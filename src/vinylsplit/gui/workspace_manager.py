from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QStackedWidget

from vinylsplit.gui.state import WorkspaceViewState
from vinylsplit.gui.workspaces import FocusedWorkspace, StudioWorkspace


class WorkspaceManager(QObject):
    """Coordinate workspace switching while preserving shared presentation state."""

    workspace_changed = Signal(str)
    state_changed = Signal(object)

    def __init__(
        self,
        stack: QStackedWidget,
        focused_workspace: FocusedWorkspace,
        studio_workspace: StudioWorkspace,
    ) -> None:
        super().__init__()
        self._stack = stack
        self._focused = focused_workspace
        self._studio = studio_workspace
        self._state = WorkspaceViewState(active_workspace="focused")

        self._focused.state_changed.connect(self._on_workspace_state_changed)
        self._studio.state_changed.connect(self._on_workspace_state_changed)

        self._stack.addWidget(self._focused)
        self._stack.addWidget(self._studio)

        self._focused.apply_state(self._state)
        self._studio.apply_state(self._state)
        self.switch_to("focused")

    @property
    def state(self) -> WorkspaceViewState:
        """Return a copy of current shared state."""

        return replace(self._state)

    def switch_to(self, workspace_id: str) -> None:
        """Switch active workspace without reloading project state."""

        if workspace_id not in {"focused", "studio"}:
            raise ValueError(f"Unsupported workspace: {workspace_id}")

        self._state.active_workspace = workspace_id
        if workspace_id == "focused":
            self._stack.setCurrentWidget(self._focused)
        else:
            self._stack.setCurrentWidget(self._studio)

        self._focused.apply_state(self._state)
        self._studio.apply_state(self._state)
        self.workspace_changed.emit(workspace_id)

    def update_state(self, state: WorkspaceViewState) -> None:
        """Replace shared state and refresh both workspace views."""

        self._state = state
        self._focused.apply_state(self._state)
        self._studio.apply_state(self._state)
        self.state_changed.emit(replace(self._state))

    def _on_workspace_state_changed(self, state: WorkspaceViewState) -> None:
        self.update_state(state)
