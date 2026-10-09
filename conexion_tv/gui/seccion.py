"""Collapsible configuration sections."""

from __future__ import annotations

from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QWidget


class SeccionColapsable(QGroupBox):
    """QGroupBox with a checkbox: unchecking hides the content."""

    def __init__(
        self,
        titulo: str,
        parent: QWidget | None = None,
        *,
        abierta: bool = True,
    ) -> None:
        super().__init__(titulo, parent)
        self.setCheckable(True)
        self.setChecked(abierta)
        self._cuerpo = QWidget(self)
        self._cuerpo_lay = QVBoxLayout(self._cuerpo)
        self._cuerpo_lay.setContentsMargins(0, 4, 0, 0)
        self._cuerpo_lay.setSpacing(6)
        externo = QVBoxLayout(self)
        externo.setContentsMargins(8, 8, 8, 8)
        externo.addWidget(self._cuerpo)
        self.toggled.connect(self._al_plegar)
        self._cuerpo.setVisible(abierta)

    @property
    def cuerpo(self) -> QVBoxLayout:
        return self._cuerpo_lay

    def _al_plegar(self, abierta: bool) -> None:
        self._cuerpo.setVisible(abierta)
