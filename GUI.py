import sys
import threading
import keyboard # Добавлена библиотека для эмуляции нажатий
import functools # Добавлено для использования partial
import time # Добавлено для задержек в потоке COM-порта
import json
import os # Добавим os для проверки существования файла

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QPushButton, QLabel, QTabWidget,
                           QGridLayout, QLineEdit, QSpacerItem, QSizePolicy,
                           QComboBox, QGroupBox, QFrame, QStackedWidget,
                           QSystemTrayIcon, QMenu) # Добавлены QGridLayout, QLineEdit, QSpacerItem, QSizePolicy, QComboBox, QGroupBox, QFrame, QStackedWidget, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer # Добавлен pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QIcon, QAction # Добавлен QAction

# Импортируем функцию обработки действий и менеджер COM-порта из action.py
from action import handle_button_action, ComManager 

class StreamDeckCompanion(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stream Deck Companion v0.6") # Обновим версию
        self.setMinimumSize(780, 550)
        self.resize(780, 550) # Задаем начальный размер окна
        
        self.minimize_on_startup = False # Флаг для автосворачивания при запуске (По умолчанию - False)
        self.tray_icon = None # Для иконки в трее
        self._force_quit = False # Флаг для принудительного выхода

        # self.signals = WorkerSignals() # Экземпляр старых сигналов (пока не нужен)
        self.selected_button_id = None # ID выбранной кнопки в UI
        # self.last_com_port = None # Перенесено в ComManager (используем self.com_manager.last_port_name)
        self._loaded_last_com_port = None # Временное хранилище для автоподключения
        
        # --- Создаем менеджер COM-порта --- 
        self.com_manager = ComManager()
        # ----------------------------------

        # --- Новые структуры для страниц --- 
        self.current_page_name = 'game' # Имя текущей активной страницы
        self.page_panels = {} # Словарь для хранения виджетов-панелей страниц {page_name: QWidget}
        self.page_buttons = {} # Словарь для хранения словарей кнопок страниц {page_name: {button_id: QPushButton}}
        # ----------------------------------

        # --- Хранилище конфигураций кнопок (теперь по страницам) ---
        # Ключ 1: Имя страницы ('main', 'game', 'chill')
        # Ключ 2: ID кнопки (1-9)
        # Значение: Словарь {'combo': str, 'icon_path': str}
        self.page_configs = {
            'main': { # Конфигурация для Main Page (пока пустая)
                i: {'combo': None, 'icon_path': None} for i in range(1, 10)
            },
            'game': { # Теперь Game Page тоже пустая по умолчанию
                i: {'combo': None, 'icon_path': None} for i in range(1, 10)
            },
            'chill': { # Конфигурация для Chill Page (пока пустая)
                 i: {'combo': None, 'icon_path': None} for i in range(1, 10)
            },
            'settings': { # Конфигурация для новой Settings Page
                i: {'combo': None, 'icon_path': None} for i in range(1, 10)
            }
        }
        # -------------------------------------

        # Создаем центральный виджет и главный layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        # === ОТСТУПЫ: Устанавливаем отступы от границ central_widget до его содержимого ===
        main_layout.setContentsMargins(2, 2, 2, 2) # 2 пикселя со всех сторон
        
        # --- Закругление углов главного окна ---
        # Примечание: Этот стиль может не повлиять на стандартные рамки окна ОС.
        # Для полного эффекта может потребоваться окно без рамок (FramelessWindowHint).
        self.setStyleSheet("""
            QMainWindow {
                border-radius: 30px; /* Радиус скругления углов */
                /* background-color: #f0f0f0; */ /* Опционально: задать цвет фона */
            }
        """)
        # ---------------------------------------

        # --- Создаем и добавляем виджет кнопок напрямую --- 
        buttons_widget = self.create_buttons_tab()
        main_layout.addWidget(buttons_widget)
        # ---------------------------------------------------

        # Добавляем элементы для статуса
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Статус: Инициализация...") # Начальный статус
        status_layout.addWidget(self.status_label)
        
        
        main_layout.addLayout(status_layout) # Добавляем layout статуса в главный layout

        # --- Подключаем сигналы от ComManager к слотам GUI --- 
        self.com_manager.signals.status_updated.connect(self._update_connection_status)
        self.com_manager.signals.port_list_updated.connect(self._update_com_port_list)
        self.com_manager.signals.data_received.connect(self._handle_serial_data)

        # --- Загружаем конфигурацию из файла ПЕРЕД автоподключением --- 
        self._load_config()
        # ----------------------------------------------------------------
        
        # --- Инициируем ПЕРВОЕ обновление списка портов --- 
        # Это нужно ДО попытки автоподключения
        # Сигнал port_list_updated вызовет слот _update_com_port_list,
        # который, в свою очередь, инициирует автоподключение, если нужно.
        self.com_manager.update_ports()
        # -----------------------------------------------------

        # --- Настройка иконки в трее --- 
        self._setup_tray_icon()
        # --------------------------------

        # --- Показать окно или свернуться при запуске --- 
        if self.minimize_on_startup:
             # Не вызываем show() сразу, а откладываем сворачивание
             QTimer.singleShot(100, self._minimize_to_tray_on_startup) # Задержка для инициализации трея
        else:
             self.show() # Показываем окно как обычно
        # -------------------------------------------------


    def create_buttons_tab(self):
        tab_widget = QWidget()
        main_hbox = QHBoxLayout(tab_widget) # Главный горизонтальный layout вкладки
        main_hbox.setSpacing(0) # Устанавливаем нулевое расстояние между левой и правой колонкой

        # --- Левая панель (кнопки страниц) ---
        left_vbox = QVBoxLayout()
        # === РАЗМЕРЫ: Расстояние между элементами в левой колонке ===
        left_vbox.setSpacing(15) # Устанавливаем расстояние между кнопками
        left_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        main_page_btn = QPushButton("Main Page")
        # === РАЗМЕРЫ: Кнопка 'Main Page' ===
        main_page_btn.setMaximumWidth(220) # Максимальная ширина
        main_page_btn.setFixedHeight(60)   # Фиксированная высота
        main_page_btn.setStyleSheet("""
            QPushButton {
                background-color: #a5d8ff; 
                color: #000000; 
                border-radius: 15px; 
                border: 1px solid #000000;
                font-family: Excalifont, sans-serif; 
                font-size: 12pt;
                font-weight: normal;
            }
            QPushButton:pressed {
                background-color: #8fbcde; /* Темнее синий */
                border: 1px solid #000000;
            }
        """)


        game_page_btn = QPushButton("Game Page")
        # === РАЗМЕРЫ: Кнопка 'Game Page' ===
        game_page_btn.setMaximumWidth(220) # Максимальная ширина
        game_page_btn.setFixedHeight(60)   # Фиксированная высота
        game_page_btn.setStyleSheet("""
            QPushButton {
                background-color: #b2f2bb; 
                color: #000000; 
                border-radius: 15px; 
                border: 1px solid #000000;
                font-family: Excalifont, sans-serif; 
                font-size: 12pt;
                font-weight: normal;
            }
            QPushButton:pressed {
                background-color: #90d09a; /* Темнее зеленый */
                border: 1px solid #000000;
            }
        """)


        chill_page_btn = QPushButton("Chill Page")
        # === РАЗМЕРЫ: Кнопка 'Chill Page' ===
        chill_page_btn.setMaximumWidth(220) # Максимальная ширина
        chill_page_btn.setFixedHeight(60)   # Фиксированная высота
        chill_page_btn.setStyleSheet("""
            QPushButton {
                background-color: #fab005; 
                color: #000000; 
                border-radius: 15px; 
                border: 1px solid #000000;
                font-family: Excalifont, sans-serif; 
                font-size: 12pt;
                font-weight: normal;
            }
            QPushButton:pressed {
                background-color: #d99a04; /* Темнее желтый */
                border: 1px solid #000000;
            }
        """)

        settings_btn = QPushButton("Settings") # Эта кнопка не для страниц SD, а для настроек компаньона
        # === РАЗМЕРЫ: Кнопка 'Settings' ===
        settings_btn.setMaximumWidth(220) # Максимальная ширина
        settings_btn.setFixedHeight(60)   # Фиксированная высота
        settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #fff5f5; 
                color: #000000; 
                border-radius: 15px; 
                border: 1px solid #000000;
                font-family: Excalifont, sans-serif; 
                font-size: 12pt;
                font-weight: normal;
            }
            QPushButton:pressed {
                background-color: #f0e0e0; /* Темнее розовый/серый */
                border: 1px solid #000000;
            }
        """)

        # --- Подключаем кнопки страниц к _switch_page --- 
        main_page_btn.clicked.connect(functools.partial(self._switch_page, "main"))
        game_page_btn.clicked.connect(functools.partial(self._switch_page, "game"))
        chill_page_btn.clicked.connect(functools.partial(self._switch_page, "chill"))
        settings_btn.clicked.connect(functools.partial(self._switch_page, "settings"))

        left_vbox.addWidget(main_page_btn)
        left_vbox.addWidget(game_page_btn)
        left_vbox.addWidget(chill_page_btn)
        left_vbox.addWidget(settings_btn)
        
        # Добавляем надпись перед блоком COM
        connection_label = QLabel("El GUI Comrado v0.6")
        connection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        connection_label.setContentsMargins(0, 25, 0, 25) # Добавить отступы сверху и снизу
        connection_label.setStyleSheet("font-family: Excalifont, sans-serif; font-size: 12pt;")
        left_vbox.addWidget(connection_label)

        # --- Настройки COM-порта (используем ComManager) ---
        com_group_box = QGroupBox("Подключение по COM-порту")
        com_group_box.setMaximumWidth(220)
        com_group_box.setFixedHeight(120)
        com_group_box.setStyleSheet("QGroupBox { font-family: Excalifont, sans-serif; font-size: 10pt; font-weight: bold; }")
        com_layout = QVBoxLayout()

        com_select_layout = QHBoxLayout()
        com_select_layout.setContentsMargins(0, 0, 0, 0)
        label_select_port = QLabel("Выберите COM-порт:")
        label_select_port.setStyleSheet("font-family: Excalifont, sans-serif; font-size: 10pt;")
        com_layout.addWidget(label_select_port)
        self.com_port_combo = QComboBox()
        # Устанавливаем начальное состояние
        self.com_port_combo.addItem("Обновление...") 
        self.com_port_combo.setEnabled(False) 
        com_select_layout.addWidget(self.com_port_combo)

        refresh_com_btn = QPushButton()
        refresh_com_btn.setIcon(QIcon.fromTheme("view-refresh"))
        refresh_com_btn.setToolTip("Обновить список портов")
        # Подключаем к методу ComManager
        refresh_com_btn.clicked.connect(self.com_manager.update_ports) 
        com_select_layout.addWidget(refresh_com_btn)
        com_layout.addLayout(com_select_layout)

        self.com_connect_btn = QPushButton("Подключить")
        self.com_connect_btn.setEnabled(False) # Изначально неактивна
        # Устанавливаем стиль для кнопки подключения
        self.com_connect_btn.setStyleSheet("""
            QPushButton {
                font-family: Excalifont, sans-serif; 
                font-size: 11pt; 
                background-color: #ce6185;
                border: 1px solid #888;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:pressed {
                 background-color: #ea1e62;
            }
            QPushButton:disabled {
                 background-color: #f0f0f0;
                 color: #a0a0a0;
            }
        """)
        # Подключаем к новому слоту
        self.com_connect_btn.clicked.connect(self._on_toggle_connection_clicked) 
        com_layout.addWidget(self.com_connect_btn)

        com_group_box.setLayout(com_layout)
        left_vbox.addWidget(com_group_box)
        left_vbox.addStretch(1)
        # ----------------------------------------------------

        # === РАЗМЕРЫ: Соотношение ширины колонок (Левая:Правая = 1:5) ===
        main_hbox.addLayout(left_vbox, 1) # Левая панель (1 часть ширины)

        # --- Правая панель (переключение страниц и редактирование) ---
        right_vbox = QVBoxLayout()
        # === РАЗМЕРЫ: Расстояние между элементами в правой колонке (Подложка и Панель редактирования) ===
        right_vbox.setSpacing(15)
        # right_vbox.setAlignment(Qt.AlignmentFlag.AlignLeft) # Удаляем выравнивание самой колонки

        # --- Создаем QStackedWidget для панелей страниц --- 
        self.page_stack = QStackedWidget()
        self.page_stack.setFixedSize(480, 285) # Задаем размер как у старой подложки
        # Добавляем стиль для фона (серый цвет), чтобы виджет был виден
        # Можно применить стиль к самому QStackedWidget или к каждой панели внутри
        self.page_stack.setStyleSheet("background-color: #e0e0e0; border-radius: 10px; border: 1px solid #000000;") 

        # --- Создаем и добавляем панели для каждой страницы --- 
        page_names = ['main', 'game', 'chill', 'settings']
        for name in page_names:
            # Вызываем метод для создания панели (будет определен позже)
            panel, buttons = self._create_button_grid_panel(name) 
            self.page_panels[name] = panel
            self.page_buttons[name] = buttons
            self.page_stack.addWidget(panel) # Добавляем панель в стопку

        # --- Устанавливаем начальную страницу --- 
        self.page_stack.setCurrentWidget(self.page_panels[self.current_page_name])

        right_vbox.addWidget(self.page_stack) # Добавляем стопку виджетов

        # --- Группа виджетов для редактирования --- 
        # Создаем QGroupBox вместо QWidget
        self.editing_group_box = QGroupBox("Редактирование кнопки")
        self.editing_group_box.setMaximumWidth(480) # Максимальная ширина (уменьшено с 550)
        self.editing_group_box.setFixedHeight(200)   # Фиксированная высота
        
        # Создаем layout и устанавливаем его для GroupBox
        editing_vbox = QVBoxLayout(self.editing_group_box) 
        # === РАЗМЕРЫ: Отступы внутри панели редактирования ===
        editing_vbox.setContentsMargins(0, 10, 0, 0) # Левый, Верхний, Правый, Нижний
        # === РАЗМЕРЫ: Расстояние между элементами в панели редактирования ===
        editing_vbox.setSpacing(10)

        # --- Комбинация клавиш --- 
        combo_label = QLabel("Введите комбинацию клавиш и нажмите Enter или Применить:")
        # === ВЫРАВНИВАНИЕ ТЕКСТА ВНУТРИ QLabel ===
        # combo_label.setAlignment(Qt.AlignmentFlag.AlignLeft)   # Выровнять текст влево (по умолчанию)
        combo_label.setAlignment(Qt.AlignmentFlag.AlignCenter) # Выровнять текст по центру
        combo_label.setContentsMargins(5, 0, 5, 1) # Левый, Верхний, Правый, Нижний

        combo_hbox = QHBoxLayout()
        self.combo_input = QLineEdit()
        # === РАЗМЕРЫ: Поле ввода комбинации клавиш ===
        self.combo_input.setFixedWidth(250) # Пример: Задать фиксированную ширину
        self.combo_input.setFixedHeight(25) # Пример: Задать фиксированную высоту
        self.combo_input.setAlignment(Qt.AlignmentFlag.AlignRight)

        #self.combo_input.setMinimumWidth(150) # Пример: Задать минимальную ширину
        # Подключаем сигнал returnPressed или кнопку "Применить"
        self.combo_input.returnPressed.connect(self._apply_key_combo)
        apply_combo_btn = QPushButton("Применить")      
        # === РАЗМЕРЫ: Кнопка 'Применить' (комбинация) ===
        apply_combo_btn.setFixedWidth(120) # Пример: Задать фиксированную ширину
        apply_combo_btn.setFixedHeight(25) # Пример: Задать фиксированную высоту
        apply_combo_btn.setStyleSheet("""
            QPushButton {
                font-family: Excalifont, sans-serif; 
                font-size: 11pt; 
                background-color: #ce6185;
                border: 1px solid #888;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:pressed {
                 background-color: #ea1e62;
            }
            QPushButton:disabled {
                 background-color: #f0f0f0;
                 color: #a0a0a0;
            }
        """)


        apply_combo_btn.clicked.connect(self._apply_key_combo)
        combo_hbox.addWidget(self.combo_input)
        combo_hbox.addWidget(apply_combo_btn)
        editing_vbox.addWidget(combo_label)
        editing_vbox.addLayout(combo_hbox)
        # === РАЗДЕЛЕНИЕ: Добавляем горизонтальную линию ===
        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine) # Горизонтальная линия
        line1.setFrameShadow(QFrame.Shadow.Sunken) # Стиль линии (вдавленная)
        editing_vbox.addWidget(line1)

        # --- Выбор иконки --- 
        icon_label = QLabel("Выбрать иконку:")
        # === ВЫРАВНИВАНИЕ ТЕКСТА ВНУТРИ QLabel ===
        # icon_label.setAlignment(Qt.AlignmentFlag.AlignLeft)   # Выровнять текст влево (по умолчанию)
        # icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter) # Выровнять текст по центру
        # icon_label.setAlignment(Qt.AlignmentFlag.AlignRight)  # Выровнять текст вправо
        icon_label.setAlignment(Qt.AlignmentFlag.AlignLeft) # Оставляем по умолчанию
        icon_hbox = QHBoxLayout()
        icon_browse_btn = QPushButton("Обзор")
        # === РАЗМЕРЫ: Кнопка 'Обзор' (иконка) ===
        # icon_browse_btn.setFixedWidth(100) # Пример: Задать фиксированную ширину
        # icon_browse_btn.setFixedHeight(25) # Пример: Задать фиксированную высоту
        icon_clear_btn = QPushButton("X")
        # === РАЗМЕРЫ: Кнопка 'X' для очистки иконки ===
        icon_clear_btn.setFixedWidth(30) # Маленькая кнопка "X" - Фиксированная ширина
        # icon_clear_btn.setFixedHeight(25) # Пример: Задать фиксированную высоту
        # TODO: Подключить кнопки обзора и очистки
        # icon_browse_btn.clicked.connect(self._browse_icon)
        # icon_clear_btn.clicked.connect(self._clear_icon)
        icon_hbox.addWidget(icon_browse_btn)
        icon_hbox.addWidget(icon_clear_btn)
        icon_hbox.addStretch(1) # Растяжитель, чтобы кнопки были слева
        editing_vbox.addWidget(icon_label)
        editing_vbox.addLayout(icon_hbox)
        # === РАЗДЕЛЕНИЕ: Добавляем горизонтальную линию ===
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        editing_vbox.addWidget(line2)

        # --- Кнопки сохранения темы и прошивки --- 
        bottom_hbox = QHBoxLayout()
        save_theme_btn = QPushButton("Сохранить тему")
        # === РАЗМЕРЫ: Кнопка 'Сохранить тему' ===
        # save_theme_btn.setFixedWidth(120) # Пример: Задать фиксированную ширину
        # save_theme_btn.setFixedHeight(30) # Пример: Задать фиксированную высоту
        flash_btn = QPushButton("Flash")
        # === РАЗМЕРЫ: Кнопка 'Flash' ===
        # flash_btn.setFixedWidth(80) # Пример: Задать фиксированную ширину
        # flash_btn.setFixedHeight(30) # Пример: Задать фиксированную высоту
        # TODO: Подключить кнопки сохранения и прошивки
        # save_theme_btn.clicked.connect(self._save_theme)
        # flash_btn.clicked.connect(self._flash_to_deck)
        bottom_hbox.addStretch(1) # Растяжитель, чтобы кнопки были справа
        bottom_hbox.addWidget(save_theme_btn)
        bottom_hbox.addWidget(flash_btn)
        editing_vbox.addLayout(bottom_hbox)

        # Настраиваем видимость и активность для GroupBox
        self.editing_group_box.setVisible(True)   # Делаем видимым по умолчанию
        self.editing_group_box.setEnabled(False)  # Делаем неактивным по умолчанию
        
        # Добавляем GroupBox в правую колонку
        right_vbox.addWidget(self.editing_group_box) 

        right_vbox.addStretch(1) # Добавляем растяжитель ВНУТРИ правой колонки, чтобы прижать контент вверх

        # === РАЗМЕРЫ: Соотношение ширины колонок (Левая:Правая = 1:5) ===
        main_hbox.addLayout(right_vbox, 5) # Правая панель (5 частей ширины)

        return tab_widget

    # --- Новый метод для создания панели кнопок ---
    def _create_button_grid_panel(self, page_name):
        """Создает панель с сеткой 3x3 кнопок для указанной страницы."""
        print(f"Создание панели для страницы: {page_name}")
        panel = QWidget()
        # Применяем стиль фона прямо к панели, а не к QStackedWidget
        # panel.setStyleSheet("background-color: #e0e0e0; border-radius: 5px;") 
        
        # --- Выбираем цвет фона в зависимости от страницы ---
        page_colors = {
            'game': '#b2f2bb',  # Светло-красный
            'main': '#a5d8ff',  # Светло-синий
            'chill': '#fab005', # Светло-зеленый
            'settings': '#fff5f5' # Светло-серый для настроек
        }
        # Получаем цвет или используем белый по умолчанию, если имя страницы неожиданное
        background_color = page_colors.get(page_name, '#ffffff') 
        
        # Устанавливаем стиль с выбранным цветом и сохраняем скругление
        panel.setStyleSheet(f"background-color: {background_color}; border-radius: 10px;")
        # ------------------------------------------------------

        grid_layout = QGridLayout(panel)
        grid_layout.setSpacing(10)
        # grid_layout.setAlignment(Qt.AlignmentFlag.AlignCenter) # Опционально

        page_specific_buttons = {} # Словарь для кнопок ЭТОЙ страницы

        for i in range(9):
            button_id = i + 1
            # Создаем кнопку, текст пока ID для отладки
            # Используем разный префикс для наглядности
            button_prefix = page_name[0].upper() if page_name != 'settings' else 'S'
            button = QPushButton(f"{button_prefix}{button_id}") 

            # Добавляем общий стиль для границ и состояний
            button.setStyleSheet("""
                QPushButton { 
                    border: 1px solid #888;
                    background-color: #f0f0f0; 
                }
                QPushButton:pressed { 
                    border: 1px solid #555;
                    background-color: #e0e0e0; 
                }
                QPushButton:checked { 
                    background-color: #a6d8f0; 
                    border: 1px solid #77a; 
                }
                QPushButton:disabled { 
                    background-color: #d0d0d0; 
                    border: 1px solid #aaa;
                    color: #888; /* Добавим серый цвет текста для неактивных */
                }
            """)

            # === РАЗМЕРЫ и Настройка для кнопок ===
            # --- Делаем ВСЕ кнопки неактивными для страницы настроек --- 
            if page_name == 'settings':
                if 1 <= button_id <= 6:
                    button.setMinimumSize(90, 90)
                else: # Для кнопок 7, 8, 9
                    button.setFixedSize(90, 30)
                button.setEnabled(False) # Все кнопки неактивны
            # --- Стандартная логика для других страниц --- 
            elif 1 <= button_id <= 6:
                button.setMinimumSize(90, 90)
                button.setCheckable(True)
                button.clicked.connect(functools.partial(self._on_deck_button_clicked, button_id))
            else: # Для кнопок 7, 8, 9 на других страницах
                button.setFixedSize(90, 30)
                button.setEnabled(False) # Оставляем неактивными по умолчанию

            page_specific_buttons[button_id] = button
            grid_layout.addWidget(button, i // 3, i % 3)

        return panel, page_specific_buttons
    # --- Конец нового метода ---

    # --- Новый метод для переключения страниц ---
    def _switch_page(self, page_name):
        """Переключает активную страницу в QStackedWidget и сбрасывает состояние UI."""
        if page_name == self.current_page_name:
             print(f"Страница {page_name} уже активна.")
             return # Ничего не делаем, если страница уже выбрана

        print(f"Переключение на страницу: {page_name}")

        # --- Сброс состояния UI перед переключением --- 
        # 1. Снять выбор с активной кнопки (если она есть) на ТЕКУЩЕЙ странице
        if self.selected_button_id:
            current_buttons = self.page_buttons.get(self.current_page_name, {})
            button_to_deselect = current_buttons.get(self.selected_button_id)
            if button_to_deselect:
                button_to_deselect.setChecked(False)

        # 2. Сбросить ID выбранной кнопки и деактивировать панель редактирования
        self.selected_button_id = None
        self.editing_group_box.setEnabled(False)
        self.combo_input.clear() # Очищаем поле ввода
        print("Состояние UI сброшено перед переключением страницы.")
        # ------------------------------------------------

        # Обновляем имя текущей страницы
        self.current_page_name = page_name

        # Находим и устанавливаем нужный виджет в QStackedWidget
        target_widget = self.page_panels.get(page_name)
        if target_widget:
            self.page_stack.setCurrentWidget(target_widget)
            print(f"Страница {page_name} установлена.")
        else:
            print(f"Ошибка: Панель для страницы {page_name} не найдена!")
    # --- Конец нового метода ---

    # --- Обработчик клика по кнопке в сетке ---
    def _on_deck_button_clicked(self, button_id):
        # --- Проверка: если нажата уже выбранная кнопка --- 
        if self.selected_button_id == button_id:
            print(f"Кнопка {button_id} уже была выбрана. Снятие выделения.")
            
            # Получаем кнопку и снимаем с нее флажок
            button_to_deselect = self.page_buttons[self.current_page_name].get(button_id)
            if button_to_deselect:
                button_to_deselect.setChecked(False)

            # Сбрасываем выбор и деактивируем панель
            self.selected_button_id = None
            self.editing_group_box.setEnabled(False)
            self.combo_input.clear() # Очищаем поле ввода для ясности
            return # Выходим из обработчика, дальше не идем
        # --- Конец проверки --- 

        # --- Если нажата ДРУГАЯ кнопка на ЭТОЙ ЖЕ странице --- 
        # Сначала снимаем выделение с ПРЕДЫДУЩЕЙ выбранной кнопки (если она была)
        if self.selected_button_id is not None:
            previous_button = self.page_buttons[self.current_page_name].get(self.selected_button_id)
            if previous_button:
                previous_button.setChecked(False)
                print(f"Снято выделение с предыдущей кнопки: {self.selected_button_id}")
        # --- Конец снятия предыдущего выделения ---

        # --- Теперь выбираем НОВУЮ кнопку --- 
        print(f"Выбрана кнопка {button_id} для редактирования")
        self.selected_button_id = button_id
        # Активируем панель редактирования (теперь это GroupBox)
        self.editing_group_box.setEnabled(True)

        # Загружаем текущую конфигурацию в поля
        config = self.page_configs[self.current_page_name].get(button_id, {'combo': '', 'icon_path': None})
        self.combo_input.setText(config.get('combo', ''))
        # TODO: Отобразить выбранную иконку (пока не реализовано)
        
    # --- Конец обработчика --- 

    # --- Метод для применения новой комбинации клавиш ---
    def _apply_key_combo(self):
        if self.selected_button_id is None:
            print("Ошибка: Кнопка для редактирования не выбрана")
            return

        new_combo = self.combo_input.text().strip().lower() # Получаем текст, убираем пробелы, приводим к нижнему регистру

        if not new_combo:
             print(f"Комбинация для кнопки {self.selected_button_id} очищена.")
             # Устанавливаем None или пустую строку, чтобы keyboard.send не вызывался
             self.page_configs[self.current_page_name][self.selected_button_id]['combo'] = None
        else:
            # TODO: Добавить валидацию строки комбинации (опционально)
            # Например, проверить, что keyboard.parse_hotkey(new_combo) не вызывает ошибку
            self.page_configs[self.current_page_name][self.selected_button_id]['combo'] = new_combo
            print(f"Для кнопки {self.selected_button_id} установлена комбинация: {new_combo}")

        # --- Новая логика для сброса UI после применения --- 
        # 1. Снять выбор с кнопки в сетке
        if self.selected_button_id in self.page_buttons[self.current_page_name]:
            button_to_deselect = self.page_buttons[self.current_page_name][self.selected_button_id]
            button_to_deselect.setChecked(False) # Снимаем флажок
        
        # 2. Очистить ID выбранной кнопки
        self.selected_button_id = None

        # 3. Сделать панель редактирования неактивной
        self.editing_group_box.setEnabled(False)
        
        # 4. Опционально: Очистить поле ввода
        # self.combo_input.clear()

        print("Выбор кнопки сброшен, панель редактирования деактивирована.")
        # -----------------------------------------------------

    # --- Конец метода --- 
        
    # --- НОВЫЕ СЛОТЫ для сигналов от ComManager --- 
    def _on_toggle_connection_clicked(self):
        """Обрабатывает клик по кнопке Подключить/Отключить."""
        if self.com_manager.is_connected:
            self.com_manager.disconnect()
        else:
            selected_index = self.com_port_combo.currentIndex()
            if selected_index >= 0:
                 port_data = self.com_port_combo.itemData(selected_index)
                 if port_data: # Убедимся, что данные не None
                      self.com_manager.connect(port_data)
                 else:
                     print("Ошибка: Не удалось получить данные для выбранного порта.")
                     self._update_connection_status("Ошибка: выберите порт", False, None)
            else:
                 print("Ошибка: Порт не выбран в комбобоксе.")
                 self._update_connection_status("Ошибка: порт не выбран", False, None)

    def _update_com_port_list(self, ports): # ports: list[tuple[str, str]]
        """Обновляет QComboBox списком портов и инициирует автоподключение."""
        print("GUI: Обновление списка портов в ComboBox...")
        current_selection_data = self.com_port_combo.currentData()
        self.com_port_combo.clear()
        
        if not ports:
            self.com_port_combo.addItem("Нет доступных портов")
            self.com_port_combo.setEnabled(False)
            self.com_connect_btn.setEnabled(False)
        else:
            for display_name, device_name in ports:
                self.com_port_combo.addItem(display_name, device_name)
            self.com_port_combo.setEnabled(not self.com_manager.is_connected)
            self.com_connect_btn.setEnabled(True)

            # Попытка восстановить выбор или выбрать последний известный
            index_to_select = -1
            port_to_autoconnect = self._loaded_last_com_port # Используем временно сохраненный порт
            
            if port_to_autoconnect:
                 print(f"GUI: Поиск загруженного порта {port_to_autoconnect} для автоподключения...")
                 for i in range(self.com_port_combo.count()):
                      if self.com_port_combo.itemData(i) == port_to_autoconnect:
                           index_to_select = i
                           break
            
            if index_to_select != -1:
                 print(f"GUI: Порт {port_to_autoconnect} найден в списке.")
                 self.com_port_combo.setCurrentIndex(index_to_select)
                 # Инициируем автоподключение ТОЛЬКО если был загружен порт и он найден
                 if port_to_autoconnect:
                     print(f"GUI: Запуск автоподключения к {port_to_autoconnect}...")
                     # Небольшая задержка может помочь UI обновиться перед подключением
                     QTimer.singleShot(50, lambda p=port_to_autoconnect: self.com_manager.connect(p))
                     # Сбрасываем временное хранилище после попытки автоподключения
                     self._loaded_last_com_port = None 
            elif port_to_autoconnect:
                print(f"GUI: Предупреждение: Загруженный порт {port_to_autoconnect} не найден в текущем списке.")
                # Сбрасываем и в менеджере, и временно сохраненный
                self.com_manager.set_last_port_name(None)
                self._loaded_last_com_port = None 
            else:
                 # Если не было загруженного порта, просто выбираем первый элемент (если он есть)
                 if self.com_port_combo.count() > 0:
                     self.com_port_combo.setCurrentIndex(0)
                 print("GUI: Нет порта для автоподключения.")

    def _update_connection_status(self, message, is_connected, port_name):
        """Обновляет статусную строку и состояние кнопок/комбобокса."""
        print(f"GUI: Обновление статуса: '{message}', Подключено: {is_connected}, Порт: {port_name}")
        self.status_label.setText(f"Статус: {message}")
        self.com_connect_btn.setText("Отключить" if is_connected else "Подключить")
        # Кнопка подключения должна быть активна, если есть порты или если мы подключены (для отключения)
        self.com_connect_btn.setEnabled(self.com_port_combo.count() > 0 and self.com_port_combo.itemText(0) != "Нет доступных портов" or is_connected)
        self.com_port_combo.setEnabled(not is_connected and self.com_port_combo.count() > 0 and self.com_port_combo.itemText(0) != "Нет доступных портов")
        
        # Обновляем сохраненное имя порта в менеджере, только если подключение УСПЕШНО
        # Или если отключились (port_name будет None)
        # ComManager сам обновляет self.last_port_name при успешном connect
        # Мы здесь можем обновить self.last_com_port для сохранения, но лучше делать это в _save_config
        # self.last_com_port = port_name # Обновляем локальную переменную? Нет, читаем из менеджера при сохранении

    # --- Конец новых слотов --- 

    def _handle_serial_data(self, data):
        """Обрабатывает данные, полученные из COM-порта (сигнал от ComManager)."""
        print(f"GUI: Обработка данных из COM: {data}")
        if data.startswith("BTN:"):
            try:
                button_id_str = data.split(':')[1]
                button_id = int(button_id_str)
                print(f"GUI: Распознан ID кнопки из COM: {button_id}")
                self._handle_button_press_ui(button_id)
            except (IndexError, ValueError) as e:
                print(f"GUI: Ошибка парсинга сообщения 'BTN:ID' из COM: {e}, данные: {data}")
        elif data.startswith("ACK:"): 
            print(f"GUI: Получено подтверждение от устройства: {data}")
        elif data.startswith("ERR:"): 
             print(f"GUI: Получена ошибка от устройства: {data}")
             self._update_connection_status(f"Ошибка устройства: {data}", self.com_manager.is_connected, self.com_manager.get_last_port_name())
        # Добавьте здесь обработку других сообщений

    # # Слот для обновления UI из основного потока (Старый, заменен на _update_connection_status)
    # def _update_status_ui(self, message):
    #     ...

    # Слот для обработки уведомлений в основном потоке (без изменений)
    def _handle_button_press_ui(self, button_id_from_device):
        # Вызываем внешнюю функцию для обработки действия
        handle_button_action(
            button_id_from_device=button_id_from_device,
            page_configs=self.page_configs,
            current_page_name=self.current_page_name,
            switch_page_callback=self._switch_page # Передаем метод для смены страницы
        )

    def closeEvent(self, event):
        """Переопределено для сворачивания в трей или выхода."""
        if self._force_quit: # Если выход инициирован из меню трея
            print("Принудительный выход...")
            # --- Корректное завершение COM-порта ПЕРЕД выходом --- 
            print("GUI: Отключение COM-порта перед выходом...")
            self.com_manager.disconnect() # Вызываем метод менеджера
            # Ждать завершения потока не нужно здесь, disconnect должен это сделать
            # -----------------------------------------------------
            
            # Сохраняем конфигурацию
            self._save_config()

            # Скрываем иконку трея
            if self.tray_icon:
                self.tray_icon.hide()
            
            print("Завершение работы принято.")
            event.accept() # Разрешаем выход
        else: # Если нажали крестик окна
            print("Сворачивание в трей...")
            event.ignore() # Игнорируем событие закрытия
            self.hide() # Скрываем окно
            if self.tray_icon:
                 self.tray_icon.showMessage(
                     "Stream Deck Companion",
                     "Приложение свернуто в трей.",
                     QSystemTrayIcon.MessageIcon.Information,
                     2000 # мс
                 )

    # --- Метод для сохранения конфигурации --- 
    def _save_config(self, filename="config.json"):
         """Сохраняет текущую конфигурацию кнопок и последний COM-порт в JSON-файл."""
         print(f"Попытка сохранения конфигурации в '{filename}'...")
         config_to_save = {
             'button_configs': self.page_configs,
             # Получаем имя порта из менеджера
             'last_com_port': self.com_manager.get_last_port_name(), 
             'minimize_on_startup': self.minimize_on_startup
         }
         try:
             with open(filename, 'w', encoding='utf-8') as f:
                 json.dump(config_to_save, f, indent=4, ensure_ascii=False)
             print(f"Конфигурация успешно сохранена в '{filename}'.")
         except IOError as e:
             print(f"Ошибка ввода/вывода при сохранении конфигурации в '{filename}': {e}")

    def _load_config(self, filename="config.json"):
        """Загружает конфигурацию кнопок и последний COM-порт из JSON-файла."""
        # Сбрасываем переменные перед загрузкой
        loaded_last_port = None
        self.minimize_on_startup = False
        default_configs = self._get_default_page_configs()
        self.page_configs = default_configs # Начинаем с дефолта

        if not os.path.exists(filename):
            print(f"Файл конфигурации '{filename}' не найден. Используется конфигурация по умолчанию.")
            self.com_manager.set_last_port_name(None) # Сообщаем менеджеру
            self._loaded_last_com_port = None
            return

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)

            # Загрузка конфигурации кнопок (логика валидации остается)
            loaded_configs = default_configs # Начинаем с дефолта для кнопок
            if isinstance(loaded_data, dict) and 'button_configs' in loaded_data:
                raw_configs = loaded_data['button_configs']
                # ... (Ваша существующая логика валидации кнопок) ...
                required_pages = {'main', 'game', 'chill', 'settings'}
                if isinstance(raw_configs, dict) and required_pages.issubset(raw_configs.keys()):
                    valid_config = True
                    temp_validated_configs = self._get_default_page_configs()
                    for page_name, page_data in raw_configs.items():
                        if page_name not in required_pages: continue
                        if not isinstance(page_data, dict): valid_config = False; break
                        temp_validated_configs[page_name] = {} 
                        for btn_id in range(1, 10):
                            btn_id_str = str(btn_id)
                            config = None
                            if btn_id_str in page_data: config = page_data[btn_id_str]
                            elif btn_id in page_data: config = page_data[btn_id]
                            if config and isinstance(config, dict) and 'combo' in config and 'icon_path' in config:
                                temp_validated_configs[page_name][btn_id] = config
                            else:
                                print(f"Предупреждение: Некорректные или отсутствующие данные для кнопки {btn_id} на странице '{page_name}'.")
                                temp_validated_configs[page_name][btn_id] = {'combo': None, 'icon_path': None}
                        if not valid_config: break
                    
                    if valid_config:
                        loaded_configs = temp_validated_configs # Используем валидную конфигурацию
                        print(f"Конфигурация кнопок успешно загружена из '{filename}'.")
                    else:
                         print(f"Ошибка: Секция 'button_configs' в '{filename}' имеет неверную структуру. Используется конфигурация кнопок по умолчанию.")
                else:
                    print(f"Ошибка: Секция 'button_configs' в '{filename}' отсутствует или неверна. Используется конфигурация кнопок по умолчанию.")
                # Загружаем остальные параметры из нового формата
                loaded_last_port = loaded_data.get('last_com_port')
                self.minimize_on_startup = loaded_data.get('minimize_on_startup', False)
                
            elif isinstance(loaded_data, dict) and 'main' in loaded_data: # Старый формат
                 print("Обнаружен старый формат config.json. Загружаются только настройки кнопок.")
                 # Логика валидации для старого формата (если нужно)
                 raw_configs = loaded_data 
                 # ... (повторить логику валидации кнопок для raw_configs) ...
                 # ... если валидно, присвоить loaded_configs ...
                 # Оставляем loaded_last_port = None и minimize_on_startup = False
            else:
                print(f"Ошибка: Неизвестный формат файла конфигурации '{filename}'. Используется конфигурация по умолчанию.")

            # Присваиваем загруженные или дефолтные конфиги
            self.page_configs = loaded_configs

            # Сохраняем загруженный порт для автоподключения и сообщаем менеджеру
            self._loaded_last_com_port = loaded_last_port 
            self.com_manager.set_last_port_name(loaded_last_port)
            print(f"Загружен последний COM-порт: {self._loaded_last_com_port}")
            print(f"Загружена настройка сворачивания при запуске: {self.minimize_on_startup}")

        except FileNotFoundError: # Этот блок теперь не должен срабатывать из-за проверки os.path.exists
             print(f"Файл конфигурации '{filename}' не найден (повторно). Используется конфигурация по умолчанию.")
             # Уже установлено по умолчанию выше
        except json.JSONDecodeError:
            print(f"Ошибка: Не удалось декодировать JSON из файла '{filename}'. Файл может быть поврежден. Используется конфигурация по умолчанию.")
            # Уже установлено по умолчанию выше
            self.com_manager.set_last_port_name(None)
            self._loaded_last_com_port = None
        except Exception as e:
            print(f"Непредвиденная ошибка при загрузке конфигурации из '{filename}': {e}. Используется конфигурация по умолчанию.")
            # Уже установлено по умолчанию выше
            self.com_manager.set_last_port_name(None)
            self._loaded_last_com_port = None

    # Вспомогательный метод для получения дефолтной конфигурации
    def _get_default_page_configs(self):
         return {
            'main': { i: {'combo': None, 'icon_path': None} for i in range(1, 10) },
            'game': { i: {'combo': None, 'icon_path': None} for i in range(1, 10) },
            'chill': { i: {'combo': None, 'icon_path': None} for i in range(1, 10) },
            'settings': { i: {'combo': None, 'icon_path': None} for i in range(1, 10) }
        }

    # --- Методы для работы с треем --- (без изменений, кроме добавления _minimize_to_tray_on_startup)
    def _setup_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("Системный трей недоступен.")
            return

        icon_path = "icon.png" # Укажите путь к вашей иконке
        if not os.path.exists(icon_path):
             print(f"Предупреждение: Файл иконки '{icon_path}' не найден. Иконка в трее не будет установлена.")
             return 
        
        self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
        self.tray_icon.setToolTip("Stream Deck Companion")

        tray_menu = QMenu()
        show_action = QAction("Показать", self)
        quit_action = QAction("Выход", self)

        show_action.triggered.connect(self.show_normal)
        quit_action.triggered.connect(self._quit_application)

        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_icon_activated)
        self.tray_icon.show()
        print("Иконка в трее успешно создана и показана.")

    def show_normal(self):
        """Показывает окно из трея."""
        self.show()
        self.activateWindow()
        self.raise_()

    def _quit_application(self):
        """Инициирует корректный выход из приложения."""
        print("Получена команда выхода из трея...")
        self._force_quit = True
        self.close() # Вызовет closeEvent
        # QApplication.instance().quit() # quit() вызывается после event loop в main

    def _tray_icon_activated(self, reason):
        """Обрабатывает клики по иконке трея."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_normal()
            
    def _minimize_to_tray_on_startup(self):
        """Сворачивает окно в трей после инициализации."""
        if self.tray_icon and self.tray_icon.isVisible():
            print("Автоматическое сворачивание в трей при запуске...")
            self.hide()
            self.tray_icon.showMessage(
                 "Stream Deck Companion",
                 "Приложение запущено и свернуто в трей.",
                 QSystemTrayIcon.MessageIcon.Information,
                 2000
            )
        else:
            print("Не удалось свернуть в трей при запуске (иконка не готова?).")
            # Можно попробовать показать окно, если трей не сработал
            self.show()


# --- Точка входа --- (без изменений)
if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Позволяет приложению работать без видимых окон (для трея)
    # app.setQuitOnLastWindowClosed(False) # Это нужно, если мы хотим ТОЛЬКО трей
                                         # Но мы хотим и окно, так что оставляем True

    window = StreamDeckCompanion()
    # window.show() # Показ окна теперь управляется в __init__ в зависимости от настроек
    
    exit_code = app.exec()
    print(f"Приложение завершено с кодом {exit_code}")
    sys.exit(exit_code)
