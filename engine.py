from copy import deepcopy


def can_place(grid, piece, row, col):
    """Проверяет, помещается ли фигура в позицию (row, col)"""
    for r in range(len(piece)):
        for c in range(len(piece[0])):
            if piece[r][c] == 1:
                if row + r >= 8 or col + c >= 8:  # за границей
                    return False
                if grid[row + r][col + c] == 1:   # занято
                    return False
    return True


def place_piece(grid, piece, row, col):
    """Возвращает новую сетку с размещённой фигурой"""
    new_grid = deepcopy(grid)
    for r in range(len(piece)):
        for c in range(len(piece[0])):
            if piece[r][c] == 1:
                new_grid[row + r][col + c] = 1
    return new_grid


def clear_lines(grid):
    """Очищает заполненные строки и столбцы"""
    # Копируем
    g = [row[:] for row in grid]
    
    # Находим полные строки
    full_rows = [r for r in range(8) if all(g[r])]
    # Находим полные столбцы
    full_cols = [c for c in range(8) if all(g[r][c] for r in range(8))]
    
    # Очищаем
    for r in full_rows:
        g[r] = [0] * 8
    for c in full_cols:
        for r in range(8):
            g[r][c] = 0
            
    return g


def solve(grid, pieces):
    """
    Возвращает список ходов [(piece_index, row, col), ...] или 0
    """
    if not pieces:
        return []
    
    piece = pieces[0]
    rest = pieces[1:]
    
    # Перебираем все позиции
    for row in range(9 - len(piece)):
        for col in range(9 - len(piece[0])):
            if can_place(grid, piece, row, col):
                new_grid = place_piece(grid, piece, row, col)
                new_grid = clear_lines(new_grid)
                
                result = solve(new_grid, rest)
                if result != 0:
                    return [(0, row, col)] + [(i+1, r, c) for i, r, c in result]
    
    return 0