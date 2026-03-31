import cv2
import numpy as np
import tempfile
import os

_board_rects = {}


def calibrate_board_rect(image_path, chat_id):
    """Находим поле для калибровки"""
    img = cv2.imread(image_path)
    rect = _find_board_rect(img)
    _board_rects[chat_id] = {'temp': rect}
    
    x, y, w, h = rect
    margin = 2
    y1, y2 = max(0, y-margin), min(img.shape[0], y+h+margin)
    x1, x2 = max(0, x-margin), min(img.shape[1], x+w+margin)
    board_img = img[y1:y2, x1:x2]
    
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False, mode='wb') as f:
        cv2.imwrite(f.name, board_img)
        return f.name, rect


def confirm_board_rect(chat_id, confirmed=True):
    """Подтверждаем положение"""
    if chat_id not in _board_rects or 'temp' not in _board_rects[chat_id]:
        return False
    
    if confirmed:
        _board_rects[chat_id]['rect'] = _board_rects[chat_id]['temp']
    
    del _board_rects[chat_id]['temp']
    return confirmed


def get_board_rect(chat_id):
    """Получить координаты"""
    if chat_id in _board_rects and 'rect' in _board_rects[chat_id]:
        return _board_rects[chat_id]['rect']
    return None


def reset_board_rect(chat_id):
    """Сброс калибровки"""
    if chat_id in _board_rects:
        del _board_rects[chat_id]


def get_board_auto(image_path, chat_id):
    """
    Авто-распознавание: находим самую частую цветовую группу = фон
    """
    rect = get_board_rect(chat_id)
    if rect is None:
        raise ValueError("Нет калибровки положения")
    
    x, y, w, h = rect
    img = cv2.imread(image_path)
    cell_w = w // 8
    cell_h = h // 8
    
    # Собираем цвета всех центров клеток
    colors = []
    for row in range(8):
        for col in range(8):
            cx = x + col * cell_w + cell_w // 2
            cy = y + row * cell_h + cell_h // 2
            color = img[cy, cx].astype(np.float32)
            colors.append((row, col, color))
    
    # Кластеризуем цвета простым способом: сортируем по яркости
    brightness = [(i, np.mean(c[2])) for i, c in enumerate(colors)]
    brightness.sort(key=lambda x: x[1])
    
    # Предполагаем: 40% самых тёмных = фон (обычно поле наполовину заполнено или меньше)
    n = len(colors)
    n_empty = max(1, n // 3)  # минимум 1/3 поля — фон
    
    # Цвет фона = средний из тёмных
    empty_indices = [b[0] for b in brightness[:n_empty]]
    empty_colors = [colors[i][2] for i in empty_indices]
    empty_color = np.mean(empty_colors, axis=0)
    
    # Распознаём
    board = []
    for row in range(8):
        board_row = []
        for col in range(8):
            idx = row * 8 + col
            cell_color = colors[idx][2]
            diff = np.abs(cell_color - empty_color)
            is_empty = np.max(diff) < 30  # чуть больше порог для надёжности
            board_row.append(0 if is_empty else 1)
        board.append(board_row)
    
    return board


def get_board_manual(image_path, chat_id, empty_row, empty_col):
    """Ручное распознавание с указанием пустой клетки (1-8)"""
    rect = get_board_rect(chat_id)
    if rect is None:
        raise ValueError("Нет калибровки положения")
    
    er, ec = empty_row - 1, empty_col - 1
    x, y, w, h = rect
    img = cv2.imread(image_path)
    cell_w = w // 8
    cell_h = h // 8
    
    ecx = x + ec * cell_w + cell_w // 2
    ecy = y + er * cell_h + cell_h // 2
    empty_color = img[ecy, ecx].astype(np.float32)
    
    board = []
    for row in range(8):
        board_row = []
        for col in range(8):
            cx = x + col * cell_w + cell_w // 2
            cy = y + row * cell_h + cell_h // 2
            cell_color = img[cy, cx].astype(np.float32)
            diff = np.abs(cell_color - empty_color)
            is_empty = np.max(diff) < 25
            board_row.append(0 if is_empty else 1)
        board.append(board_row)
    
    return board


def _find_board_rect(img):
    """Поиск поля"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 21, 5)
    
    kernel = np.ones((5,5), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    best_rect = None
    best_score = 0
    
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw < 100 or ch < 100:
            continue
        
        squareness = min(cw, ch) / max(cw, ch)
        if squareness < 0.7:
            continue
        
        roi = gray[y:y+ch, x:x+cw]
        has_grid = _check_grid_pattern(roi)
        score = cw * ch * squareness * (2 if has_grid else 0.5)
        
        center_y = y + ch/2
        position_bonus = 1.0 if center_y > h * 0.2 else 0.5
        score *= position_bonus
        
        if score > best_score:
            best_score = score
            best_rect = (x, y, cw, ch)
    
    if best_rect is None:
        size = int(min(h, w) * 0.5)
        x = (w - size) // 2
        y = int(h * 0.25)
        best_rect = (x, y, size, size)
    
    return best_rect


def _check_grid_pattern(roi_gray):
    """Проверка сетки"""
    if roi_gray.shape[0] < 50 or roi_gray.shape[1] < 50:
        return False
    
    grad_x = np.abs(np.diff(roi_gray.astype(float), axis=1))
    grad_y = np.abs(np.diff(roi_gray.astype(float), axis=0))
    
    proj_x = np.mean(grad_x, axis=0)
    proj_y = np.mean(grad_y, axis=1)
    
    peaks_x = _count_peaks(proj_x, np.mean(proj_x)*2)
    peaks_y = _count_peaks(proj_y, np.mean(proj_y)*2)
    
    return 7 <= peaks_x <= 11 and 7 <= peaks_y <= 11


def _count_peaks(arr, threshold):
    count = 0
    for i in range(1, len(arr)-1):
        if arr[i] > threshold and arr[i] > arr[i-1] and arr[i] > arr[i+1]:
            count += 1
    return count


def get_figures(image_path):
    return []