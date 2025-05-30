from django import template

register = template.Library()

@register.filter
def zip_lists(a, b):
    return zip(a, b)

@register.filter
def get_bingo_colors(value):
    """Returns a list of tuples containing letters and their corresponding colors."""
    colors = {
        'B': '#FF6B6B',  # Red
        'I': '#4ECDC4',  # Teal
        'N': '#FFD93D',  # Yellow
        'G': '#95E1D3',  # Mint
        'O': '#FF8B94',  # Pink
    }
    return [(char, colors[char]) for char in value]

@register.filter
def to(value, end):
    """Returns a range from value to end."""
    try:
        return range(int(value), int(end) + 1)
    except (ValueError, TypeError):
        return []

@register.filter
def multiply(value, arg):
    """Multiply the value by the argument"""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def get_bingo_number(column, row):
    """Calculate the number for a given position in the BINGO grid
    B: 1-15
    I: 16-30
    N: 31-45
    G: 46-60
    O: 61-75
    """
    try:
        col_num = int(column)
        row_num = int(row)
        return (col_num - 1) * 15 + row_num
    except (ValueError, TypeError):
        return 0