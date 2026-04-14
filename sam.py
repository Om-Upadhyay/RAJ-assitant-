from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QPushButton,
    QLineEdit,
    QMenu,
    QSystemTrayIcon,
    QAction,
    QStyle,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QEvent
import sys
import threading
from listener import listen
from commands import execute_command
from speak import speak
from wake_listener import detect_wake_word

class SAM_GUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RAJ - AI Assistant")
        self.setGeometry(300, 100, 980, 560)
        self.setStyleSheet(
            """
            QWidget {
                background: #0b0f1a;
                color: #e6f1ff;
                font-family: "Segoe UI";
            }
            QFrame#card {
                background: #121a2b;
                border: 1px solid #1f2a44;
                border-radius: 16px;
            }
            QLabel#title {
                font-size: 26px;
                font-weight: 600;
            }
            QLabel#subtitle {
                color: #9fb3d9;
                font-size: 13px;
            }
            QLabel#statusBadge {
                background: #1b2a4a;
                border-radius: 12px;
                padding: 6px 12px;
                color: #d6e4ff;
            }
            QLabel#pulse {
                background: #1f6feb;
                border-radius: 8px;
                min-width: 16px;
                max-width: 16px;
                min-height: 16px;
                max-height: 16px;
            }
            QLabel#waveform {
                font-size: 18px;
                color: #7aa2ff;
                letter-spacing: 3px;
            }
            QPushButton#actionButton {
                background: #1f6feb;
                border-radius: 10px;
                padding: 10px 16px;
                font-weight: 600;
            }
            QPushButton#ghostButton {
                background: transparent;
                border: 1px solid #2b3b5e;
                border-radius: 10px;
                padding: 10px 16px;
                color: #c9d5ee;
            }
            QLineEdit#commandInput {
                background: #0f1626;
                border: 1px solid #233252;
                border-radius: 10px;
                padding: 10px 12px;
                color: #e6f1ff;
            }
            """
        )

        header = QLabel("RAJ Assistant")
        header.setObjectName("title")

        subtitle = QLabel("Always-on desktop companion for Windows")
        subtitle.setObjectName("subtitle")

        title_layout = QVBoxLayout()
        title_layout.addWidget(header)
        title_layout.addWidget(subtitle)
        title_layout.setSpacing(4)
        title_layout.setContentsMargins(0, 0, 0, 0)

        self.status_badge = QLabel("Waiting for wake word: 'Hey RAJ'")
        self.status_badge.setObjectName("statusBadge")

        self.pulse = QLabel()
        self.pulse.setObjectName("pulse")

        pulse_layout = QHBoxLayout()
        pulse_layout.addWidget(self.pulse)
        pulse_layout.addWidget(self.status_badge)
        pulse_layout.addStretch()
        pulse_layout.setSpacing(10)

        self.waveform = QLabel("▁ ▂ ▃ ▄ ▅ ▆ ▇ ▆ ▅ ▄ ▃ ▂ ▁")
        self.waveform.setObjectName("waveform")
        self.waveform.setAlignment(Qt.AlignCenter)

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QVBoxLayout(status_card)
        status_layout.addLayout(title_layout)
        status_layout.addSpacing(12)
        status_layout.addLayout(pulse_layout)
        status_layout.addSpacing(24)
        status_layout.addWidget(self.waveform)
        status_layout.addStretch()

        activity_card = QFrame()
        activity_card.setObjectName("card")
        activity_layout = QVBoxLayout(activity_card)
        activity_layout.addWidget(self._section_title("Recent activity"))
        activity_layout.addWidget(self._activity_row("• Waiting for your command"))
        activity_layout.addWidget(self._activity_row("• Wake word: Hey RAJ"))
        activity_layout.addWidget(self._activity_row("• Mode: Background listening"))
        activity_layout.addSpacing(18)
        activity_layout.addWidget(self._section_title("Quick controls"))

        controls_layout = QHBoxLayout()
        wake_button = self._action_button("Wake / Listen")
        wake_button.clicked.connect(self.respond)
        controls_layout.addWidget(wake_button)
        controls_layout.addWidget(self._action_button("Mute Mic"))
        controls_layout.addWidget(self._ghost_button("Settings"))
        quit_button = self._ghost_button("Quit")
        quit_button.clicked.connect(self.shutdown_app)
        controls_layout.addWidget(quit_button)
        activity_layout.addLayout(controls_layout)
        activity_layout.addSpacing(18)
        activity_layout.addWidget(self._section_title("Type a command"))

        input_layout = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setObjectName("commandInput")
        self.command_input.setPlaceholderText("Type a command and press Enter")
        self.command_input.returnPressed.connect(self.handle_text_command)
        self.command_input.installEventFilter(self)
        send_button = self._action_button("Send")
        send_button.clicked.connect(self.handle_text_command)
        input_layout.addWidget(self.command_input, 1)
        input_layout.addWidget(send_button)
        activity_layout.addLayout(input_layout)
        activity_layout.addStretch()

        main_layout = QHBoxLayout()
        main_layout.addWidget(status_card, 3)
        main_layout.addWidget(activity_card, 2)
        main_layout.setSpacing(24)
        main_layout.setContentsMargins(24, 24, 24, 24)

        self.setLayout(main_layout)

        self.is_listening = False
        self.cancel_listening = False
        self.typing_active = False
        self.state_listeners = []
        self.update_state("🧠 Waiting for wake word: 'Hey RAJ'", "#1f6feb")

        threading.Thread(target=self.wake_loop, daemon=True).start()

    def wake_loop(self):
        detect_wake_word(self.respond)

    def respond(self):
        if self.typing_active:
            self.update_state("⌨️ Typing mode (listening paused)", "#1f6feb")
            return
        if self.is_listening:
            return
        self.is_listening = True
        self.update_state("🎙 Listening...", "#19c37d")

        # Start a new thread for listening and processing
        threading.Thread(target=self.handle_user_command, daemon=True).start()

    def handle_user_command(self):
        while True:
            if self.cancel_listening:
                self.cancel_listening = False
                break
            self.update_state("🎙 Listening...", "#19c37d")

            query = listen()  # This blocks until user finishes speaking

            if query:
                self.update_state("🤖 Processing...", "#f59e0b")
                print(f"User said: {query}")
                speak("You said " + query)

                if "exit" in query.lower():
                    speak("Okay, going to sleep.")
                    break  # Exit loop, back to wake word mode

                execute_command(query, speak)
            else:
                self.update_state("⚠️ I didn’t catch that.", "#ef4444")
                speak("Sorry, I didn’t catch that.")

        # Only after exit
        if self.typing_active:
            self.update_state("⌨️ Typing mode (listening paused)", "#1f6feb")
        else:
            self.update_state("🧠 Waiting for wake word: 'Hey RAJ'", "#1f6feb")
        self.is_listening = False

    def handle_text_command(self):
        query = self.command_input.text().strip()
        if not query:
            return

        self.command_input.clear()
        self.update_state("🤖 Processing...", "#f59e0b")
        print(f"User typed: {query}")
        speak("You said " + query)

        if "exit" in query.lower():
            speak("Okay, going to sleep.")
            self.update_state("🧠 Waiting for wake word: 'Hey RAJ'", "#1f6feb")
            return

        threading.Thread(
            target=execute_command,
            args=(query, speak),
            daemon=True,
        ).start()

    def stop_listening_for_typing(self):
        if self.is_listening:
            self.cancel_listening = True
        self.update_state("⌨️ Typing mode (listening paused)", "#1f6feb")

    def eventFilter(self, obj, event):
        if obj is self.command_input:
            if event.type() == QEvent.FocusIn:
                self.typing_active = True
                self.stop_listening_for_typing()
            elif event.type() == QEvent.FocusOut:
                self.typing_active = False
                if not self.is_listening:
                    self.update_state("🧠 Waiting for wake word: 'Hey RAJ'", "#1f6feb")
        return super().eventFilter(obj, event)

    def update_state(self, text, color):
        self.status_badge.setText(text)
        self.pulse.setStyleSheet(f"background: {color}; border-radius: 8px;")
        if "Listening" in text:
            self.waveform.setText("▁ ▃ ▅ ▇ █ ▇ ▅ ▃ ▁")
        elif "Processing" in text:
            self.waveform.setText("▂ ▃ ▄ ▅ ▆ ▇ ▆ ▅ ▄ ▃ ▂")
        else:
            self.waveform.setText("▁ ▂ ▃ ▄ ▅ ▆ ▇ ▆ ▅ ▄ ▃ ▂ ▁")

        for listener in self.state_listeners:
            listener(text, color)

    def add_state_listener(self, listener):
        self.state_listeners.append(listener)

    def shutdown_app(self):
        QApplication.quit()

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def _section_title(self, text):
        label = QLabel(text)
        label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        return label

    def _activity_row(self, text):
        label = QLabel(text)
        label.setObjectName("subtitle")
        return label

    def _action_button(self, text):
        button = QPushButton(text)
        button.setObjectName("actionButton")
        return button

    def _ghost_button(self, text):
        button = QPushButton(text)
        button.setObjectName("ghostButton")
        return button


class DesktopWidget(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(120, 120)
        self.setObjectName("desktopWidget")

        self.button = QPushButton("RAJ")
        self.button.setObjectName("floatingButton")
        self.button.clicked.connect(self.controller.respond)

        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("statusText")
        self.status_label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addWidget(self.button)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.setStyleSheet(
            """
            QWidget#desktopWidget {
                background: transparent;
            }
            QPushButton#floatingButton {
                background: #1f6feb;
                border: 2px solid #0b0f1a;
                border-radius: 32px;
                color: #ffffff;
                font-weight: 600;
                min-width: 64px;
                min-height: 64px;
                max-width: 64px;
                max-height: 64px;
            }
            QLabel#statusText {
                color: #c9d5ee;
                font-size: 11px;
            }
            """
        )

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)

    def show_menu(self, pos):
        menu = QMenu(self)
        open_action = menu.addAction("Open Panel")
        quit_action = menu.addAction("Quit")
        action = menu.exec_(self.mapToGlobal(pos))
        if action == open_action:
            self.controller.show()
            self.controller.raise_()
            self.controller.activateWindow()
        elif action == quit_action:
            self.controller.shutdown_app()

    def update_state(self, text, color):
        text_lower = text.lower()
        if "listening" in text_lower:
            label = "Listening"
        elif "processing" in text_lower:
            label = "Processing"
        elif "typing" in text_lower:
            label = "Typing"
        else:
            label = "Idle"
        self.status_label.setText(label)
        self.button.setStyleSheet(
            f"background: {color}; border: 2px solid #0b0f1a; border-radius: 32px; color: #ffffff; font-weight: 600; min-width: 64px; min-height: 64px; max-width: 64px; max-height: 64px;"
        )
     
if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = SAM_GUI()
    gui.show()
    widget = DesktopWidget(gui)
    gui.add_state_listener(widget.update_state)
    screen = app.primaryScreen()
    if screen:
        geometry = screen.availableGeometry()
        x = geometry.right() - widget.width() - 24
        y = geometry.bottom() - widget.height() - 48
        widget.move(x, y)
    widget.show()
    tray_icon = QSystemTrayIcon()
    tray_icon.setIcon(app.style().standardIcon(QStyle.SP_ComputerIcon))
    tray_icon.setToolTip("RAJ Assistant")

    tray_menu = QMenu()
    open_panel_action = QAction("Open Panel")
    open_panel_action.triggered.connect(lambda: (gui.show(), gui.raise_(), gui.activateWindow()))
    wake_action = QAction("Wake / Listen")
    wake_action.triggered.connect(gui.respond)
    quit_action = QAction("Quit")
    quit_action.triggered.connect(gui.shutdown_app)
    tray_menu.addAction(open_panel_action)
    tray_menu.addAction(wake_action)
    tray_menu.addSeparator()
    tray_menu.addAction(quit_action)
    tray_icon.setContextMenu(tray_menu)
    tray_icon.show()

    def handle_tray_activate(reason):
        if reason == QSystemTrayIcon.Trigger:
            gui.show()
            gui.raise_()
            gui.activateWindow()

    tray_icon.activated.connect(handle_tray_activate)
    sys.exit(app.exec_())

