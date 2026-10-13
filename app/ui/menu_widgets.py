"""Lowercase presentation for mergen's controls; model identifiers stay intact."""
from PySide6 import QtWidgets


def menu_text(text: str) -> str:
    return text.replace('İ', 'i').lower()


class _Text:
    def __init__(self, *args, **kwargs):
        if args and isinstance(args[0], str):
            args = (menu_text(args[0]), *args[1:])
        super().__init__(*args, **kwargs)

    def setText(self, text):
        super().setText(menu_text(text))

    def setToolTip(self, text):
        super().setToolTip(menu_text(text))


class MenuLabel(_Text, QtWidgets.QLabel):
    pass


class MenuButton(_Text, QtWidgets.QPushButton):
    pass


class MenuCheckBox(_Text, QtWidgets.QCheckBox):
    pass


class MenuGroupBox(_Text, QtWidgets.QGroupBox):
    pass


class MenuComboBox(QtWidgets.QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSizeAdjustPolicy(self.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(14)

    def addItem(self, text, userData=None):
        super().addItem(menu_text(text), userData)

    def setItemText(self, index, text):
        super().setItemText(index, menu_text(text))

    def setToolTip(self, text):
        super().setToolTip(menu_text(text))


class MenuFormLayout(QtWidgets.QFormLayout):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setRowWrapPolicy(self.RowWrapPolicy.WrapLongRows)

    def addRow(self, *args):
        if args and isinstance(args[0], str):
            args = (menu_text(args[0]), *args[1:])
        super().addRow(*args)
