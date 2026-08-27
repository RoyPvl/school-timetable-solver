from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from school_timetable_solver.desktop_composition import DesktopApplicationComposition


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("SchoolTimetableSolver")
    app.setApplicationName("時間割解決システム")

    data_location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    data_directory = Path(data_location) if data_location else Path.home() / ".school-timetable-solver"
    window = DesktopApplicationComposition().create_desktop_window(data_directory)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
