import sys
import os
from pathlib import Path
from PySide6.QtCore import QCoreApplication, Qt, QTimer, QLockFile
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPen
from PySide6.QtWidgets import QApplication, QMessageBox
from imagesearch.ui import Window
from imagesearch.store import data_root


def main():
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName('ImageSearch'); app.setOrganizationName('ImageSearch')
    app.setStyle('Fusion')
    root=data_root(); root.mkdir(parents=True,exist_ok=True)
    lock=QLockFile(str(root/'app.lock'))
    if not lock.tryLock(0):
        QMessageBox.information(None,'ImageSearch','이미 실행 중입니다. 열려 있는 ImageSearch 창을 확인해 주세요.')
        return
    pix = QPixmap(128,128); pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor('#30273e')); p.setPen(Qt.PenStyle.NoPen); p.drawRoundedRect(4,4,120,120,30,30)
    p.setPen(QPen(QColor('#c6acf4'),8)); p.drawEllipse(31,28,51,51); p.drawLine(76,75,99,99); p.end()
    app.setWindowIcon(QIcon(pix))
    window=Window(); window.show()
    smoke=os.environ.get('IMAGESEARCH_SMOKE_OUTPUT')
    if smoke:
        def capture():
            window.grab().save(smoke)
            window.close()
            QTimer.singleShot(200,app.quit)
        QTimer.singleShot(2500,capture)
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
