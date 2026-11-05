"""Vertical sweep for boxes that may constrain one another's horizontal lanes."""


def vertical_neighbors(blocks):
    neighbors = [[] for _ in blocks]
    active = []
    for index in sorted(range(len(blocks)), key=lambda i: blocks[i]['y']):
        box = blocks[index]
        top, height = box['y'], box['h']
        active = [i for i in active if blocks[i]['y'] + blocks[i]['h'] > top]
        for other_index in active:
            other = blocks[other_index]
            overlap = min(top + height, other['y'] + other['h']) - top
            if overlap > min(height, other['h']) * .25:
                neighbors[index].append(other_index)
                neighbors[other_index].append(index)
        active.append(index)
    return neighbors
