import cv2
import os
import numpy as np
import threading   # ✅ ADD THIS LINE
from HandTracker import HandDetector
from dottedline import drawrect, drawline
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QFileDialog, QComboBox, QSlider, QHBoxLayout, QFrame, QSizePolicy, QDialog, QGridLayout, QLineEdit, QMessageBox, QCheckBox
from PyQt5.QtGui import QImage, QPixmap, QIcon, QFont, QPainter, QColor
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
import sys
from pptx import Presentation
import tempfile
import shutil
import fitz  # PyMuPDF
import subprocess

class GestureCustomizationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize Gestures")
        self.setGeometry(250, 250, 500, 400)
        self.setStyleSheet("background-color: #2C2F33; color: #FFFFFF; font-family: Arial, sans-serif;")
        self.parent = parent

        if not hasattr(parent, 'custom_gestures'):
            parent.custom_gestures = {
                'next_slide': [0, 0, 0, 0, 1],
                'previous_slide': [1, 0, 0, 0, 0],
                'clear_annotations': [1, 1, 1, 1, 1],
                'toggle_guide': [1, 1, 0, 0, 0],
            }
        self.custom_gestures = parent.custom_gestures

        layout = QGridLayout(self)
        self.action_checks = {}
        self.finger_labels = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']

        actions = ['Next Slide', 'Previous Slide', 'Clear Annotations', 'Toggle Guide']
        for row, action in enumerate(actions):
            label = QLabel(f"{action}:")
            label.setStyleSheet("font-size: 14px; color: #FFFFFF;")
            layout.addWidget(label, row, 0)

            check_layout = QHBoxLayout()
            key = action.lower().replace(' ', '_')
            current_gesture = self.custom_gestures.get(key, [0, 0, 0, 0, 0])
            self.action_checks[key] = {}
            for col, (finger, state) in enumerate(zip(self.finger_labels, current_gesture)):
                cb = QCheckBox(finger)
                cb.setStyleSheet("color: #FFFFFF;")
                cb.setChecked(bool(state))
                cb.stateChanged.connect(lambda state, a=action, f=finger: self.update_preview(a, f))
                cb.setToolTip(f"Check to raise the {finger.lower()} for {action}")
                self.action_checks[key][finger] = cb
                check_layout.addWidget(cb)
            layout.addLayout(check_layout, row, 1)

        self.preview_label = QLabel()
        self.preview_label.setStyleSheet("background-color: #36393F; border: 2px solid #1E90FF; border-radius: 5px;")
        self.preview_label.setFixedSize(200, 200)
        self.update_preview(actions[0])
        layout.addWidget(self.preview_label, 0, 2, 4, 1)

        save_button = QPushButton("Save")
        save_button.setIcon(QIcon(os.path.join("icons", "save.png")))
        save_button.setStyleSheet("""
            QPushButton {
                background-color: #43B581; color: white; padding: 10px; border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #3CA374;
            }
        """)
        save_button.clicked.connect(self.save_gestures)
        layout.addWidget(save_button, 4, 0, 1, 3)

        self.setLayout(layout)

    def update_preview(self, action, changed_finger=None):
        key = action.lower().replace(' ', '_')
        gesture = [int(self.action_checks[key][f].isChecked()) for f in self.finger_labels]
        self.custom_gestures[key] = gesture

        hand_path = os.path.join("images", "hand.png")
        if os.path.exists(hand_path):
            pixmap = QPixmap(hand_path).scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter = QPainter(pixmap)
            painter.setPen(QColor(255, 0, 0))
            painter.setBrush(QColor(255, 0, 0, 100))

            finger_positions = [
                QPoint(50, 50),  # Thumb
                QPoint(80, 50),  # Index
                QPoint(110, 50), # Middle
                QPoint(140, 50), # Ring
                QPoint(170, 50)  # Pinky
            ]
            for i, (state, pos) in enumerate(zip(gesture, finger_positions)):
                if state:
                    painter.drawEllipse(pos, 10, 10)
            painter.end()
            self.preview_label.setPixmap(pixmap)
        else:
            self.preview_label.setText("Hand image not found")

    def save_gestures(self):
        try:
            self.parent.custom_gestures = self.custom_gestures
            QMessageBox.information(self, "Success", "Gestures saved successfully!")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save gestures: {str(e)}")
            print(f"Error in save_gestures: {str(e)}")

class OptionsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gesture-Controlled Presentation Setup")
        self.setGeometry(200, 200, 600, 500)
        self.setStyleSheet("background-color: #2C2F33; color: #FFFFFF; font-family: Arial, sans-serif;")
        self.custom_gestures = {
            'next_slide': [0, 0, 0, 0, 1],
            'previous_slide': [1, 0, 0, 0, 0],
            'clear_annotations': [1, 1, 1, 1, 1],
            'toggle_guide': [1, 1, 0, 0, 0],
        }

        # Variables
        self.ppt_path = ""
        self.temp_dir = None
        self.slide_paths = []
        self.webcam_id = 0
        self.detection_conf = 0.5
        self.annotation_color = (0, 0, 255)
        self.camera_available = False

        # Check default camera
        self.check_camera()

        # GUI Setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # Header
        header = QLabel("Gesture Presentation System")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #1E90FF; padding: 10px;")
        header.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(header)

        # PPT Selection
        ppt_frame = QFrame()
        ppt_frame.setStyleSheet("background-color: #36393F; border-radius: 8px; padding: 15px;")
        ppt_layout = QVBoxLayout(ppt_frame)
        self.select_button = QPushButton("Select PPT File")
        self.select_button.setIcon(QIcon(os.path.join("icons", "open-file.png")))
        self.select_button.setStyleSheet("""
            QPushButton {
                background-color: #7289DA; color: white; padding: 10px; border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #677BC4;
            }
        """)
        self.select_button.clicked.connect(self.select_ppt)
        ppt_layout.addWidget(self.select_button)

        self.ppt_label = QLabel("No PPT selected")
        self.ppt_label.setStyleSheet("font-size: 12px; color: #B9BBBE; padding: 5px;")
        self.ppt_label.setAlignment(Qt.AlignCenter)
        ppt_layout.addWidget(self.ppt_label)
        self.layout.addWidget(ppt_frame)

        # Gesture Sensitivity
        sensitivity_frame = QFrame()
        sensitivity_frame.setStyleSheet("background-color: #36393F; border-radius: 8px; padding: 15px;")
        sensitivity_layout = QVBoxLayout(sensitivity_frame)
        self.sensitivity_label = QLabel(f"Gesture Sensitivity: {self.detection_conf:.2f}")
        self.sensitivity_label.setStyleSheet("font-size: 14px; color: #FFFFFF;")
        sensitivity_layout.addWidget(self.sensitivity_label)

        self.sensitivity_slider = QSlider(Qt.Horizontal)
        self.sensitivity_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #4A4D55; height: 8px; border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #1E90FF; width: 16px; border-radius: 8px;
                margin: -4px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #4682B4;
            }
        """)
        self.sensitivity_slider.setMinimum(50)
        self.sensitivity_slider.setMaximum(95)
        self.sensitivity_slider.setValue(60)
        self.sensitivity_slider.valueChanged.connect(self.update_sensitivity)
        sensitivity_layout.addWidget(self.sensitivity_slider)
        self.layout.addWidget(sensitivity_frame)

        # Annotation Color
        color_frame = QFrame()
        color_frame.setStyleSheet("background-color: #36393F; border-radius: 8px; padding: 15px;")
        color_layout = QVBoxLayout(color_frame)
        self.color_label = QLabel("Annotation Color:")
        self.color_label.setStyleSheet("font-size: 14px; color: #FFFFFF;")
        color_layout.addWidget(self.color_label)

        self.color_combo = QComboBox()
        self.color_combo.setStyleSheet("background-color: #4A4D55; color: #FFFFFF; padding: 5px; border-radius: 5px;")
        self.color_combo.addItems(["Red", "Blue", "Green", "Yellow"])
        self.color_combo.currentTextChanged.connect(self.update_color)
        color_layout.addWidget(self.color_combo)
        self.layout.addWidget(color_frame)

        # Customize Gestures
        gesture_frame = QFrame()
        gesture_frame.setStyleSheet("background-color: #36393F; border-radius: 8px; padding: 15px;")
        gesture_layout = QVBoxLayout(gesture_frame)
        self.customize_button = QPushButton("Customize Gestures")
        self.customize_button.setIcon(QIcon(os.path.join("icons", "settings.png")))
        self.customize_button.setStyleSheet("""
            QPushButton {
                background-color: #7289DA; color: white; padding: 10px; border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #677BC4;
            }
        """)
        self.customize_button.clicked.connect(self.show_gesture_customization)
        gesture_layout.addWidget(self.customize_button)
        self.layout.addWidget(gesture_frame)

        # Start Button
        self.start_button = QPushButton("Start Presentation")
        self.start_button.setIcon(QIcon(os.path.join("icons", "play.png")))
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #43B581; color: white; padding: 12px; border-radius: 5px;
                font-size: 16px; font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3CA374;
            }
            QPushButton:disabled {
                background-color: #4A4D55; color: #7F858E;
            }
        """)
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_presentation)
        self.layout.addWidget(self.start_button)

        # Status
        self.status_label = QLabel("Please select a PPT file")
        self.status_label.setStyleSheet("font-size: 12px; color: #FFA500; padding: 5px; background-color: #40444B; border-radius: 5px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.status_label)

        self.layout.addStretch()

    def check_camera(self):
        """Verify default camera availability."""
        cap = cv2.VideoCapture(self.webcam_id)
        self.camera_available = cap.isOpened()
        cap.release()
        if not self.camera_available:
            self.status_label.setText("No camera detected")
            self.start_button.setEnabled(False)

    def update_sensitivity(self):
        """Update gesture sensitivity."""
        self.detection_conf = self.sensitivity_slider.value() / 100
        self.sensitivity_label.setText(f"Gesture Sensitivity: {self.detection_conf:.2f}")

    def update_color(self, color):
        """Update annotation color."""
        color_map = {
            "Red": (0, 0, 255),
            "Blue": (255, 0, 0),
            "Green": (0, 255, 0),
            "Yellow": (0, 255, 255)
        }
        self.annotation_color = color_map[color]
        self.status_label.setText(f"Annotation color: {color}")

    def select_ppt(self):
        """Open file dialog to select PPT."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select PPT File", "", "PowerPoint Files (*.ppt *.pptx)")
        if file_path:
            if file_path.lower().endswith(('.ppt', '.pptx')):
                try:
                    Presentation(file_path)
                    self.ppt_path = file_path
                    self.ppt_label.setText(os.path.basename(file_path))
                    self.start_button.setEnabled(self.camera_available)
                    self.status_label.setText("PPT selected successfully")
                except Exception as e:
                    self.status_label.setText("Invalid PPT file")
                    print(f"Error selecting PPT: {str(e)}")
                    self.ppt_path = ""
                    self.start_button.setEnabled(False)
            else:
                self.status_label.setText("Please select a .ppt or .pptx file")
                self.ppt_path = ""
                self.start_button.setEnabled(False)

    def show_gesture_customization(self):
        """Show gesture customization dialog."""
        try:
            print(f"Opening gesture dialog, custom_gestures: {self.custom_gestures}")
            dialog = GestureCustomizationDialog(self)
            dialog.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open gesture customization: {str(e)}")
            print(f"Error opening gesture dialog: {str(e)}")

    def convert_ppt_to_images(self):
        """Convert PPT to images via PDF using LibreOffice."""
        if not self.ppt_path:
            return False
        self.temp_dir = tempfile.mkdtemp()
        pdf_path = os.path.join(self.temp_dir, "temp.pdf")

        libreoffice_path = r"C:\Program Files\LibreOffice\program\soffice.exe"
        if not os.path.exists(libreoffice_path):
            self.status_label.setText("LibreOffice not found at default path")
            return False

        try:
            subprocess.run([
                libreoffice_path, "--headless", "--convert-to", "pdf",
                "--outdir", self.temp_dir, self.ppt_path
            ], check=True, capture_output=True, text=True)
            pdf_name = os.path.splitext(os.path.basename(self.ppt_path))[0] + ".pdf"
            pdf_path = os.path.join(self.temp_dir, pdf_name)
            if not os.path.exists(pdf_path):
                self.status_label.setText("PDF conversion failed")
                return False
        except subprocess.CalledProcessError as e:
            self.status_label.setText(f"PPT conversion failed: {e.stderr}")
            return False
        except Exception as e:
            self.status_label.setText(f"PPT conversion failed: {str(e)}")
            return False

        try:
            doc = fitz.open(pdf_path)
            self.slide_paths = []
            for i in range(doc.page_count):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_path = os.path.join(self.temp_dir, f"slide_{i}.png")
                pix.save(img_path)
                self.slide_paths.append(img_path)
            doc.close()
            return len(self.slide_paths) > 0
        except Exception as e:
            self.status_label.setText(f"PDF to image failed: {str(e)}")
            return False

    def start_presentation(self):
        """Convert PPT and launch presentation."""
        self.status_label.setText("Converting PPT...")
        if self.convert_ppt_to_images():
            self.status_label.setText("Starting presentation...")
            self.hide()
            self.presentation_window = PresentationGUI(
                self.slide_paths, self.temp_dir, self.webcam_id,
                self.detection_conf, self.annotation_color, self.custom_gestures
            )
            self.presentation_window.show()
        else:
            self.status_label.setText("Failed to process PPT")

    def closeEvent(self, event):
        """Clean up temporary files."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        event.accept()

class PresentationGUI(QMainWindow):
    def __init__(self, slide_paths, temp_dir, webcam_id, detection_conf, annotation_color, custom_gestures):
        super().__init__()
        self.setWindowTitle("Gesture-Controlled Presentation")
        self.setGeometry(100, 100, 1280, 720)
        self.setStyleSheet("background-color: #2C2F33; color: #FFFFFF; font-family: Arial, sans-serif;")
        self.temp_dir = temp_dir
        self.custom_gestures = custom_gestures

        # Variables
        self.width, self.height = 1280, 720
        self.slide_paths = slide_paths
        self.slide_num = 0
        self.hs, self.ws = int(120 * 1.2), int(213 * 1.2)
        self.ge_thresh_y = int(self.hs * 0.8)
        self.ge_thresh_x = int(self.ws * 0.8)
        self.gest_done = False
        self.gest_counter = 0
        self.delay = 10
        self.annotations = [[]]
        self.annot_num = 0
        self.annot_start = False
        self.show_guide = False
        self.gesture_feedback = ""
        self.feedback_timer = 0
        self.annotation_color = annotation_color

        # Camera Setup
        self.cap = cv2.VideoCapture(webcam_id)
        if not self.cap.isOpened():
            self.gesture_feedback = "Camera not available"
            self.feedback_timer = 100
        else:
            self.cap.set(3, self.ws)
            self.cap.set(4, self.hs)

        # HandDetector
        self.detector = HandDetector(detectionCon=detection_conf, maxHands=1)

        # GUI Setup
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        self.layout.setContentsMargins(10, 10, 10, 10)

        # Slide Display
        self.slide_label = QLabel()
        self.slide_label.setStyleSheet("background-color: #36393F; border: 2px solid #1E90FF; border-radius: 10px;")
        self.slide_label.setFixedSize(self.width - 200, self.height)
        self.slide_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.slide_label)

        # Control Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("background-color: #40444B; border-radius: 8px;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(10)

        # Navigation Buttons
        nav_frame = QFrame()
        nav_frame.setStyleSheet("background-color: #2C2F33; border-radius: 5px;")
        nav_layout = QHBoxLayout(nav_frame)
        self.prev_button = QPushButton()
        self.prev_button.setIcon(QIcon(os.path.join("icons", "left-arrow.png")))
        self.prev_button.setStyleSheet("""
            QPushButton {
                background-color: #7289DA; color: white; padding: 15px; border-radius: 5px;
                qproperty-iconSize: 24px;
            }
            QPushButton:hover {
                background-color: #677BC4;
            }
        """)
        self.prev_button.clicked.connect(self.prev_slide)
        nav_layout.addWidget(self.prev_button)

        self.next_button = QPushButton()
        self.next_button.setIcon(QIcon(os.path.join("icons", "right-arrow.png")))
        self.next_button.setStyleSheet("""
            QPushButton {
                background-color: #7289DA; color: white; padding: 15px; border-radius: 5px;
                qproperty-iconSize: 24px;
            }
            QPushButton:hover {
                background-color: #677BC4;
            }
        """)
        self.next_button.clicked.connect(self.next_slide)
        nav_layout.addWidget(self.next_button)
        sidebar_layout.addWidget(nav_frame)

        # Clear Button
        self.clear_button = QPushButton("Clear")
        self.clear_button.setIcon(QIcon(os.path.join("icons", "erase.png")))
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #F04747; color: white; padding: 10px; border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
        """)
        self.clear_button.clicked.connect(self.clear_annotations)
        sidebar_layout.addWidget(self.clear_button)

        # Guide Button
        self.guide_button = QPushButton("Guide")
        self.guide_button.setIcon(QIcon(os.path.join("icons", "info.png")))
        self.guide_button.setStyleSheet("""
            QPushButton {
                background-color: #43B581; color: white; padding: 10px; border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #3CA374;
            }
        """)
        self.guide_button.clicked.connect(self.toggle_guide)
        sidebar_layout.addWidget(self.guide_button)

        # Status Label with Animation
        self.status_label = QLabel("Status: Waiting for gesture")
        self.status_label.setStyleSheet("font-size: 12px; color: #FFA500; padding: 5px; background-color: #2C2F33; border-radius: 5px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(self.status_label)

        sidebar_layout.addStretch()
        self.layout.addWidget(sidebar)

        # Timer for updating frames
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(20)

        # Thread for gesture processing
        self.running = True
        self.thread = threading.Thread(target=self.process_gestures)
        self.thread.daemon = True
        self.thread.start()

        # Current frames
        self.slide_current = None
        self.frame = None

    def cv2_to_qimage(self, cv_img):
        """Convert OpenCV image to QImage."""
        if cv_img is None:
            return QImage()
        cv_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, c = cv_img.shape
        bytes_per_line = c * w
        return QImage(cv_img.data, w, h, bytes_per_line, QImage.Format_RGB888)

    def next_slide(self):
        """Manually go to next slide."""
        if self.slide_num < len(self.slide_paths) - 1:
            self.slide_num += 1
            self.annotations = [[]]
            self.annot_num = 0
            self.gesture_feedback = "Next slide"
            self.feedback_timer = 30
            self.animate_status()

    def prev_slide(self):
        """Manually go to previous slide."""
        if self.slide_num > 0:
            self.slide_num -= 1
            self.annotations = [[]]
            self.annot_num = 0
            self.gesture_feedback = "Previous slide"
            self.feedback_timer = 30
            self.animate_status()

    def clear_annotations(self):
        """Clear all annotations."""
        if self.annotations:
            self.annotations = [[]]
            self.annot_num = 0
            self.gesture_feedback = "Annotations cleared"
            self.feedback_timer = 30
            self.animate_status()

    def toggle_guide(self):
        """Toggle gesture guide."""
        self.show_guide = not self.show_guide
        self.gesture_feedback = "Guide toggled" if self.show_guide else "Guide hidden"
        self.feedback_timer = 30
        self.animate_status()

    def animate_status(self):
        """Animate status label for feedback."""
        anim = QPropertyAnimation(self.status_label, b"geometry")
        anim.setDuration(200)
        anim.setStartValue(self.status_label.geometry())
        anim.setEndValue(self.status_label.geometry().adjusted(0, -10, 0, 10))
        anim.setEasingCurve(QEasingCurve.OutInQuad)
        anim.start()

    def process_gestures(self):
        """Process gestures in a separate thread with hold detection."""
        self.last_gesture = None
        self.gesture_hold_counter = 0
        self.hold_threshold = 15  # frames to hold gesture before triggering

        while self.running:
            if not self.cap.isOpened():
                self.slide_current = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                cv2.putText(self.slide_current, "Camera not available", (50, self.height // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                continue

            success, frame = self.cap.read()
            if not success:
                continue
            frame = cv2.flip(frame, 1)
            frame_h, frame_w, _ = frame.shape

            slide_current = cv2.imread(self.slide_paths[self.slide_num])
            if slide_current is None:
                continue
            slide_current = cv2.resize(slide_current, (self.width - 200, self.height))

            hands, frame = self.detector.findHands(frame)
            drawrect(frame, (frame_w, 0), (self.ge_thresh_x, self.ge_thresh_y), (0, 255, 0), 5, 'dotted')

            current_gesture = None
            detected_gesture = "None"

            if hands:
                hand = hands[0]
                cx, cy = hand["center"]
                lm_list = hand["lmList"]
                fingers = self.detector.fingersUp(hand)

                index_x = lm_list[8][0]
                index_y = lm_list[8][1]
                x_val = int(np.interp(index_x, [0, frame_w], [0, self.width - 200]))
                y_val = int(np.interp(index_y, [0, frame_h], [0, self.height]))
                index_fing = (x_val, y_val)

                # Detect which gesture is currently held
                if cy < self.ge_thresh_y and cx > self.ge_thresh_x:
                    if fingers == self.custom_gestures.get('previous_slide', [1, 0, 0, 0, 0]):
                        current_gesture = 'previous_slide'
                    elif fingers == self.custom_gestures.get('next_slide', [0, 0, 0, 0, 1]):
                        current_gesture = 'next_slide'
                    elif fingers == self.custom_gestures.get('clear_annotations', [1, 1, 1, 1, 1]):
                        current_gesture = 'clear_annotations'
                    elif fingers == self.custom_gestures.get('toggle_guide', [1, 1, 0, 0, 0]):
                        current_gesture = 'toggle_guide'

                # Gesture hold detection logic
                if current_gesture == self.last_gesture and current_gesture is not None:
                    self.gesture_hold_counter += 1
                else:
                    self.gesture_hold_counter = 1
                    self.last_gesture = current_gesture

                if self.gesture_hold_counter >= self.hold_threshold and not self.gest_done:
                    self.gest_done = True
                    self.gesture_hold_counter = 0
                    self.last_gesture = None

                    if current_gesture == 'previous_slide' and self.slide_num > 0:
                        self.slide_num -= 1
                        detected_gesture = "Previous"
                        self.gesture_feedback = "Previous slide"
                    elif current_gesture == 'next_slide' and self.slide_num < len(self.slide_paths) - 1:
                        self.slide_num += 1
                        detected_gesture = "Next"
                        self.gesture_feedback = "Next slide"
                    elif current_gesture == 'clear_annotations':
                        self.annotations = [[]]
                        self.annot_num = 0
                        detected_gesture = "Clear"
                        self.gesture_feedback = "Annotations cleared"
                    elif current_gesture == 'toggle_guide':
                        self.show_guide = not self.show_guide
                        detected_gesture = "Guide Toggle"
                        self.gesture_feedback = "Guide toggled" if self.show_guide else "Guide hidden"

                    self.feedback_timer = 30

                # Drawing gesture (index finger)
                if fingers == [0, 1, 0, 0, 0]:
                    if not self.annot_start:
                        self.annot_start = True
                        self.annot_num += 1
                        self.annotations.append([])
                    self.annotations[self.annot_num].append(index_fing)
                    cv2.circle(slide_current, index_fing, 4, self.annotation_color, cv2.FILLED)
                    self.gesture_feedback = "Drawing"
                    self.feedback_timer = 30
                    detected_gesture = "Draw"
                elif self.annot_start and fingers != [0, 1, 0, 0, 0]:
                    self.annot_start = False

                #Pointer
                if fingers == [0, 1, 1, 0, 0]:
                    cv2.circle(slide_current, index_fing, 5, self.annotation_color, -1)
                    cv2.circle(slide_current, index_fing, 7, self.annotation_color, 1, lineType=cv2.LINE_AA)
                    self.gesture_feedback = "Pointer active"
                    self.feedback_timer = 30
                    detected_gesture = "Pointer"

                # Erase
                if fingers == [0, 1, 1, 1, 0] and self.annotations:
                    if self.annot_num >= 0:
                        self.annotations.pop(-1)
                        self.annot_num -= 1
                        self.gest_done = True
                        self.gesture_feedback = "Annotation erased"
                        self.feedback_timer = 30
                        detected_gesture = "Erase"

                cv2.putText(frame, f"Gesture: {detected_gesture}", (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            if self.gest_done:
                self.gest_counter += 1
                if self.gest_counter > self.delay:
                    self.gest_counter = 0
                    self.gest_done = False

            for annotation in self.annotations:
                for j in range(1, len(annotation)):
                    drawline(slide_current, annotation[j - 1], annotation[j], self.annotation_color, thickness=6,
                             style='dotted')
                    cv2.circle(slide_current, annotation[j], 4, self.annotation_color, cv2.FILLED)

            img_small = cv2.resize(frame, (self.ws, self.hs))
            slide_current[self.height - self.hs:self.height, self.width - 200 - self.ws:self.width - 200] = img_small

            if self.feedback_timer > 0:
                cv2.putText(slide_current, self.gesture_feedback, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (255, 255, 255), 2)

            if self.show_guide:
                overlay = slide_current.copy()
                cv2.rectangle(overlay, (10, 10), (260, 190), (255, 255, 255), -1)
                cv2.rectangle(overlay, (10, 10), (260, 190), (0, 0, 0), 2)
                y = 30
                cv2.putText(overlay, "Gesture Guide:", (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
                y += 20
                for text in [
                    f"Custom Previous: {self.custom_gestures.get('previous_slide', [1, 0, 0, 0, 0])}",
                    f"Custom Next: {self.custom_gestures.get('next_slide', [0, 0, 0, 0, 1])}",
                    f"Custom Clear: {self.custom_gestures.get('clear_annotations', [1, 1, 1, 1, 1])}",
                    f"Custom Toggle Guide: {self.custom_gestures.get('toggle_guide', [1, 1, 0, 0, 0])}",
                    "Index+Middle: Pointer",
                    "Index up: Draw",
                    "Index+Middle+Ring: Erase"
                ]:
                    cv2.putText(overlay, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
                    y += 20
                alpha = 0.8
                slide_current = cv2.addWeighted(overlay, alpha, slide_current, 1 - alpha, 0)

            self.slide_current = slide_current
            self.frame = frame

    def update_frame(self):
        """Update GUI with current frames."""
        if self.slide_current is not None:
            slide_qimage = self.cv2_to_qimage(self.slide_current)
            self.slide_label.setPixmap(QPixmap.fromImage(slide_qimage))
        if self.feedback_timer > 0:
            self.feedback_timer -= 1
            self.status_label.setText(f"Status: {self.gesture_feedback}")
            self.animate_status()
        else:
            self.status_label.setText("Status: Waiting for gesture")

    def closeEvent(self, event):
#         """Clean up on window close."""
        self.running = False
        if self.cap.isOpened():
            self.cap.release()
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QMainWindow {
            background-color: #2C2F33;
         }
        QFrame {
             border: none;
         }
     """)
    window = OptionsWindow()
    window.show()
    sys.exit(app.exec_())