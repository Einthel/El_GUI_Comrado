import sys
# import asyncio # Убрано
# import bleak # Убрано
import threading
# import qasync # Убрано
import keyboard # Добавлена библиотека для эмуляции нажатий
import functools # Добавлено для использования partial
import time # Добавлено для задержек в потоке COM-порта
import serial # Добавлено для работы с COM-портом
import serial.tools.list_ports # Добавлено для поиска COM-портов
import json
import os # Добавим os для проверки существования файла

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QPushButton, QLabel, QTabWidget,
                           QGridLayout, QLineEdit, QSpacerItem, QSizePolicy,
                           QComboBox, QGroupBox, QFrame, QStackedWidget,
                           QSystemTrayIcon, QMenu) # Добавлены QGridLayout, QLineEdit, QSpacerItem, QSizePolicy, QComboBox, QGroupBox, QFrame, QStackedWidget, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer # Добавлен pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QIcon, QAction # Добавлен QAction

# --- UUID из прошивки --- # Удалено
# SERVICE_UUID           = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
# CHARACTERISTIC_UUID_TX = "beb5483e-36e1-4688-b7f5-ea07361b26a8" # Для получения ID кнопок (Notify)
# CHARACTERISTIC_UUID_RX = "c1a7a3a5-9d1a-4c0b-8a0a-3e1e1b0a3d6e" # Для отправки команд (Write)
# ------------------------- # Удалено

# Добавляем класс для сигналов, чтобы безопасно обновлять UI из другого потока
class WorkerSignals(QObject):
    # update_status = pyqtSignal(bool, str) # Сигнал для обновления статуса (connected, message) - Заменено на общий статус
    update_status = pyqtSignal(str) # Новый сигнал для обновления статуса (просто строка)
    # button_pressed = pyqtSignal(int) # Новый сигнал для ID нажатой кнопки - Убрано, используем serial_data_received
    serial_data_received = pyqtSignal(str) # Сигнал для данных из COM-порта

# # ПЛЕЙСХОЛДЕРЫ: Замените их на реальные UUID вашего Stream Deck
# BUTTON_SERVICE_UUID = "0000xxxx-0000-1000-8000-00805f9b34fb" 
# BUTTON_CHARACTERISTIC_UUID = "0000yyyy-0000-1000-8000-00805f9b34fb"

class StreamDeckCompanion(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stream Deck Companion v0.3") # Обновим версию
        self.setMinimumSize(820, 600)
        self.resize(820, 600) # Задаем начальный размер окна
        
        self.minimize_on_startup = False # Флаг для автосворачивания при запуске (По умолчанию - False)
        self.tray_icon = None # Для иконки в трее
        self._force_quit = False # Флаг для принудительного выхода

        self.signals = WorkerSignals() # Создаем экземпляр сигналов
        self.selected_button_id = None # ID выбранной кнопки в UI
        self.last_com_port = None # Имя последнего подключенного COM-порта (для автоподключения)

        # --- Переменные для COM-порта ---
        self.serial_port = None # Объект serial.Serial для активного порта
        self.serial_thread = None # Поток для чтения из COM-порта
        self.available_com_ports = [] # Список доступных COM-портов
        self.is_serial_connected = False # Флаг состояния подключения COM
        self._stop_serial_thread = threading.Event() # Событие для остановки потока COM
        # --------------------------------

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
            }
        }
        # -------------------------------------

        # Создаем центральный виджет и главный layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        # === ОТСТУПЫ: Устанавливаем отступы от границ central_widget до его содержимого ===
        main_layout.setContentsMargins(2, 2, 2, 2) # 2 пикселя со всех сторон
        
        # Создаем вкладки
        tabs = QTabWidget()
        main_layout.addWidget(tabs)
        
        # Добавляем вкладки
        tabs.addTab(self.create_buttons_tab(), "Кнопки")
       
        tabs.addTab(self.create_settings_tab(), "Настройки")

        # Добавляем элементы для статуса
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Статус: Не подключено")
        status_layout.addWidget(self.status_label)
        
        
        main_layout.addLayout(status_layout) # Добавляем layout статуса в главный layout

        # Подключаем сигнал к слоту обновления UI
        self.signals.update_status.connect(self._update_status_ui)
        # Подключаем сигнал получения данных (COM) к обработчику
        self.signals.serial_data_received.connect(self._handle_serial_data)

        # Обновляем список COM-портов при старте (будет вызвано при создании вкладки настроек)
        # self._update_com_ports() # Вызовем позже из create_settings_tab
        
        # --- Загружаем конфигурацию из файла в самом конце __init__ ---
        self._load_config()
        # -------------------------------------------------------------
        
        # --- Попытка автоподключения ---
        # Убедимся, что список портов обновлен ПЕРЕД попыткой найти порт
        # Поскольку _update_com_ports вызывается в create_buttons_tab,
        # а create_buttons_tab вызывается ДО этой точки, список должен быть актуален.
        if self.last_com_port and self.com_port_combo.count() > 0:
            print(f"Найден сохраненный порт: {self.last_com_port}. Попытка автоподключения...")
            # Ищем индекс порта в QComboBox по сохраненному имени (port_device)
            index_to_select = -1
            for i in range(self.com_port_combo.count()):
                # .itemData(i) возвращает данные, которые мы сохранили (port.device)
                if self.com_port_combo.itemData(i) == self.last_com_port:
                    index_to_select = i
                    break

            if index_to_select != -1:
                print(f"Порт {self.last_com_port} найден в списке. Выбор и подключение...")
                self.com_port_combo.setCurrentIndex(index_to_select)
                # Небольшая задержка перед вызовом подключения, чтобы UI успел обновиться (опционально)
                # time.sleep(0.1)
                self._toggle_com_port_connection() # Инициируем подключение
            else:
                print(f"Предупреждение: Сохраненный порт {self.last_com_port} не найден в текущем списке доступных портов.")
                self.last_com_port = None # Сбрасываем, раз порт не найден
        elif self.last_com_port:
            print(f"Предупреждение: Сохранен порт {self.last_com_port}, но нет доступных портов для подключения.")
            self.last_com_port = None # Сбрасываем

        # --- Настройка иконки в трее --- 
        self._setup_tray_icon()
        # --------------------------------

        # -------------------------------------------------------------

    def create_buttons_tab(self):
        tab_widget = QWidget()
        main_hbox = QHBoxLayout(tab_widget) # Главный горизонтальный layout вкладки

        # --- Левая панель (кнопки страниц) ---
        left_vbox = QVBoxLayout()
        # === РАЗМЕРЫ: Расстояние между элементами в левой колонке ===
        left_vbox.setSpacing(15) # Устанавливаем расстояние между кнопками
        left_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        main_page_btn = QPushButton("Main Page")
        # === РАЗМЕРЫ: Кнопка 'Main Page' ===
        main_page_btn.setMaximumWidth(220) # Максимальная ширина
        main_page_btn.setFixedHeight(60)   # Фиксированная высота
        game_page_btn = QPushButton("Game Page")
        # === РАЗМЕРЫ: Кнопка 'Game Page' ===
        game_page_btn.setMaximumWidth(220) # Максимальная ширина
        game_page_btn.setFixedHeight(60)   # Фиксированная высота
        chill_page_btn = QPushButton("Chill Page")
        # === РАЗМЕРЫ: Кнопка 'Chill Page' ===
        chill_page_btn.setMaximumWidth(220) # Максимальная ширина
        chill_page_btn.setFixedHeight(60)   # Фиксированная высота
        settings_btn = QPushButton("Settings") # Эта кнопка не для страниц SD, а для настроек компаньона
        # === РАЗМЕРЫ: Кнопка 'Settings' ===
        settings_btn.setMaximumWidth(220) # Максимальная ширина
        settings_btn.setFixedHeight(60)   # Фиксированная высота

        # --- Подключаем кнопки страниц к _switch_page --- 
        main_page_btn.clicked.connect(functools.partial(self._switch_page, "main"))
        game_page_btn.clicked.connect(functools.partial(self._switch_page, "game"))
        chill_page_btn.clicked.connect(functools.partial(self._switch_page, "chill"))
        # settings_btn.clicked.connect(self._open_companion_settings) # Пока оставим

        left_vbox.addWidget(main_page_btn)
        left_vbox.addWidget(game_page_btn)
        left_vbox.addWidget(chill_page_btn)
        left_vbox.addWidget(settings_btn)
        
        # Добавляем надпись перед блоком COM
        connection_label = QLabel("El GUI Comrado v0.5")
        connection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        connection_label.setContentsMargins(0, 25, 0, 25) # Добавить отступы сверху и снизу
        left_vbox.addWidget(connection_label)

        # --- Настройки COM-порта (перемещено сюда) ---
        com_group_box = QGroupBox("Подключение по COM-порту")
        # === РАЗМЕРЫ: Панель 'Подключение по COM-порту' ===
        com_group_box.setMaximumWidth(220) # Максимальная ширина
        com_group_box.setFixedHeight(120) # Фиксированная высота
        
        #com_group_box.setAlignment(Qt.AlignmentFlag.AlignCenter) # Выравнивание по центру
        com_layout = QVBoxLayout()  

        # Горизонтальный layout для выбора порта и обновления
        com_select_layout = QHBoxLayout()
        com_select_layout.setContentsMargins(0, 0, 0, 0) # Удаляем отступы
        com_layout.addWidget(QLabel("Выберите COM-порт:"))
        self.com_port_combo = QComboBox()
        com_select_layout.addWidget(self.com_port_combo)
        
        refresh_com_btn = QPushButton()
        refresh_com_btn.setIcon(QIcon.fromTheme("view-refresh")) # Стандартная иконка обновления
        refresh_com_btn.setToolTip("Обновить список портов")
        refresh_com_btn.clicked.connect(self._update_com_ports)
        com_select_layout.addWidget(refresh_com_btn)
        com_layout.addLayout(com_select_layout)

        # Кнопка подключения/отключения
        self.com_connect_btn = QPushButton("Подключить")
        self.com_connect_btn.clicked.connect(self._toggle_com_port_connection)
        com_layout.addWidget(self.com_connect_btn)
        
        com_group_box.setLayout(com_layout)

        left_vbox.addWidget(com_group_box) # Добавляем в левую панель
        left_vbox.addStretch(1) # Растягиваем пространство ПОД группой COM-порта
        # -------------------------------------------
        
        # Обновляем список COM-портов при создании вкладки
        self._update_com_ports()

        # === РАЗМЕРЫ: Соотношение ширины колонок (Левая:Правая = 1:5) ===
        main_hbox.addLayout(left_vbox, 1) # Левая панель (1 часть ширины)

        # --- Правая панель (переключение страниц и редактирование) ---
        right_vbox = QVBoxLayout()
        # === РАЗМЕРЫ: Расстояние между элементами в правой колонке (Подложка и Панель редактирования) ===
        right_vbox.setSpacing(15)
        # right_vbox.setAlignment(Qt.AlignmentFlag.AlignLeft) # Удаляем выравнивание самой колонки

        # --- Создаем QStackedWidget для панелей страниц --- 
        self.page_stack = QStackedWidget()
        self.page_stack.setFixedSize(550, 285) # Задаем размер как у старой подложки
        # Добавляем стиль для фона (серый цвет), чтобы виджет был виден
        # Можно применить стиль к самому QStackedWidget или к каждой панели внутри
        self.page_stack.setStyleSheet("background-color: #e0e0e0; border-radius: 5px;") 

        # --- Создаем и добавляем панели для каждой страницы --- 
        page_names = ['main', 'game', 'chill']
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
        self.editing_group_box.setMaximumWidth(550) # Максимальная ширина
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
        # combo_label.setAlignment(Qt.AlignmentFlag.AlignRight)  # Выровнять текст вправо
        # combo_label.setAlignment(Qt.AlignmentFlag.AlignJustify)# Выровнять текст по ширине (редко используется для коротких меток)
        #combo_label.setAlignment(Qt.AlignmentFlag.AlignLeft) # Оставляем по умолчанию
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

        grid_layout = QGridLayout(panel)
        grid_layout.setSpacing(10)
        # grid_layout.setAlignment(Qt.AlignmentFlag.AlignCenter) # Опционально

        page_specific_buttons = {} # Словарь для кнопок ЭТОЙ страницы

        for i in range(9):
            button_id = i + 1
            # Создаем кнопку, текст пока ID для отладки
            button = QPushButton(f"{page_name[0].upper()}{button_id}") # Например, G1, M1, C1

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
                }
            """)

            # === РАЗМЕРЫ и Настройка для кнопок 1-6 и 7-9 ===
            if 1 <= button_id <= 6:
                button.setMinimumSize(90, 90)
                button.setCheckable(True)
                # Не используем setAutoExclusive
                # Подключаем сигнал к _on_deck_button_clicked
                button.clicked.connect(functools.partial(self._on_deck_button_clicked, button_id))
            else: # Для кнопок 7, 8, 9
                button.setFixedSize(90, 30)
                button.setEnabled(False)

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

        # Сбрасываем выбор других кнопок (если не используется AutoExclusive)
        # for id, btn in self.deck_buttons.items():
        #     if id != button_id:
        #         btn.setChecked(False)
        
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

    # --- Метод для отправки команды на Stream Deck --- # УДАЛЕНО
    # def _send_command_to_deck(self, command: str):
    #     print(f"Отправка команды: {command}")
    #     # Отправка через COM-порт (если нужно будет отправлять команды)
    #     if self.is_serial_connected and self.serial_port:
    #          try:
    #              self.serial_port.write(f"{command}\n".encode('utf-8'))
    #              print(f"Команда '{command}' отправлена через COM-порт.")
    #          except serial.SerialException as e:
    #              print(f"Ошибка записи в COM-порт: {e}")
    #              self.signals.update_status.emit(f"Ошибка записи COM: {e}")
    #     else:
    #         print("Ошибка: COM-порт не подключен для отправки команды.")
    #         self.signals.update_status.emit("Ошибка: COM-порт не подключен")
    # --- Конец методов отправки --- # УДАЛЕНО

        
    def create_settings_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        

        # TODO: Добавить другие общие настройки, если нужно
        layout.addWidget(QLabel("Здесь могут быть другие настройки приложения"))

        layout.addStretch(1) # Добавляем растяжитель вниз
        return widget

    # --- Методы для работы с COM-портом ---
    def _update_com_ports(self):
        """Сканирует и обновляет список доступных COM-портов в QComboBox."""
        print("Обновление списка COM-портов...")
        self.com_port_combo.clear()
        self.available_com_ports = serial.tools.list_ports.comports()
        if not self.available_com_ports:
            self.com_port_combo.addItem("Нет доступных портов")
            self.com_port_combo.setEnabled(False)
            self.com_connect_btn.setEnabled(False)
        else:
            for port in self.available_com_ports:
                self.com_port_combo.addItem(f"{port.device} - {port.description}", port.device)
            self.com_port_combo.setEnabled(not self.is_serial_connected) # Разблокируем выбор, если не подключены
            self.com_connect_btn.setEnabled(True)
        print(f"Найдено портов: {len(self.available_com_ports)}")

    def _toggle_com_port_connection(self):
        """Подключается к выбранному COM-порту или отключается от текущего."""
        if self.is_serial_connected:
            # --- Отключение ---
            print("Отключение от COM-порта...")
            self._stop_serial_thread.set() # Сигнализируем потоку об остановке
            if self.serial_thread:
                self.serial_thread.join() # Ждем завершения потока
                self.serial_thread = None
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                print(f"Порт {self.serial_port.port} закрыт.")
            self.serial_port = None
            self.is_serial_connected = False
            self._stop_serial_thread.clear()
            self.com_connect_btn.setText("Подключить")
            self.com_port_combo.setEnabled(True) # Разблокируем выбор порта
            self.status_label.setText("Статус: COM-порт отключен")
            self.last_com_port = None # Сбрасываем имя порта при ручном отключении
            print("COM-порт отключен.")
        else:
            # --- Подключение ---
            selected_index = self.com_port_combo.currentIndex()
            if selected_index < 0 or not self.available_com_ports:
                print("Ошибка: Не выбран COM-порт для подключения.")
                self.status_label.setText("Статус: Ошибка - порт не выбран")
                return

            port_device = self.com_port_combo.currentData() # Получаем имя устройства (e.g., 'COM3')
            print(f"Попытка подключения к {port_device}...")
            try:
                # Подключаемся к порту. Укажите нужную скорость (baudrate), таймаут и другие параметры.
                # 115200 - стандартная скорость для ESP32 в вашем .ino файле.
                self.serial_port = serial.Serial(port_device, 115200, timeout=1)
                time.sleep(2) # Даем время на инициализацию порта

                if self.serial_port.is_open:
                    self.is_serial_connected = True
                    self.com_connect_btn.setText("Отключить")
                    self.com_port_combo.setEnabled(False) # Блокируем выбор во время подключения
                    self.status_label.setText(f"Статус: Подключено к {port_device}")
                    print(f"Успешно подключено к {port_device}.")
                    
                    # Запускаем поток для чтения данных
                    self._stop_serial_thread.clear()
                    self.serial_thread = threading.Thread(target=self._read_from_com_port_thread, daemon=True)
                    self.serial_thread.start()
                    # Сохраняем имя успешно подключенного порта
                    self.last_com_port = port_device
                    print(f"Имя порта {self.last_com_port} сохранено для автоподключения.")
                else:
                    self.status_label.setText(f"Статус: Ошибка подключения к {port_device}")
                    print(f"Не удалось открыть порт {port_device}.")
                    self.serial_port = None

            except serial.SerialException as e:
                print(f"Ошибка SerialException при подключении к {port_device}: {e}")
                self.status_label.setText(f"Статус: Ошибка - {e}")
                self.serial_port = None
            except Exception as e:
                print(f"Неизвестная ошибка при подключении к {port_device}: {e}")
                self.status_label.setText(f"Статус: Неизвестная ошибка подключения")
                self.serial_port = None

    def _read_from_com_port_thread(self):
        """Функция, выполняемая в отдельном потоке для чтения данных из COM-порта."""
        print("Поток чтения COM-порта запущен.")
        while not self._stop_serial_thread.is_set():
            if self.serial_port and self.serial_port.is_open:
                try:
                    if self.serial_port.in_waiting > 0:
                        # Читаем строку до символа новой строки ('\n')
                        line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                        if line:
                            print(f"[COM Recv]: {line}") # Выводим полученные данные
                            # Отправляем сигнал в основной поток
                            self.signals.serial_data_received.emit(line)
                    else:
                        # Небольшая пауза, чтобы не загружать процессор
                        time.sleep(0.05) 
                except serial.SerialException as e:
                    print(f"Ошибка чтения из COM-порта: {e}")
                    # Возможно, стоит сигнализировать об ошибке в UI или попробовать переподключиться
                    self._stop_serial_thread.set() # Останавливаем поток при ошибке
                    # Отправляем сигнал для обновления UI об ошибке
                    # Используем существующий update_status, но можно и отдельный
                    self.signals.update_status.emit(f"Ошибка COM: {e}")
                    break # Выходим из цикла
                except Exception as e:
                    print(f"Неизвестная ошибка в потоке чтения COM: {e}")
                    self._stop_serial_thread.set()
                    self.signals.update_status.emit(f"Критическая ошибка COM")
                    break # Выходим из цикла
            else:
                # Если порт закрылся по какой-то причине
                print("Порт закрыт, поток чтения COM останавливается.")
                break
        print("Поток чтения COM-порта завершен.")

    def _handle_serial_data(self, data):
        """Обрабатывает данные, полученные из COM-порта."""
        print(f"Обработка данных из COM: {data}")
        if data.startswith("BTN:"):
            try:
                # Извлекаем ID после "BTN:"
                button_id_str = data.split(':')[1]
                button_id = int(button_id_str)
                print(f"Распознан ID кнопки из COM: {button_id}")
                # Передаем ID в общий обработчик нажатий
                self._handle_button_press_ui(button_id)
            except (IndexError, ValueError) as e:
                print(f"Ошибка парсинга сообщения 'BTN:ID' из COM: {e}, данные: {data}")
        elif data.startswith("ACK:"): # Пример обработки подтверждений от устройства
            print(f"Получено подтверждение от устройства: {data}")
        elif data.startswith("ERR:"): # Пример обработки ошибок от устройства
             print(f"Получена ошибка от устройства: {data}")
             # Можно добавить вывод ошибки в статусную строку
             # self.status_label.setText(f"Статус: Ошибка устройства - {data}")
        # Добавьте здесь обработку других сообщений от устройства, если необходимо
    # --- Конец методов COM-порта ---

    # Слот для обновления UI из основного потока
    def _update_status_ui(self, message):
        # Просто отображаем полученное сообщение в статусной строке
        self.status_label.setText(f"Статус: {message}")
        print(f"Статус: {message}") # Дополнительно выводим в консоль

        # Обновляем состояние UI в зависимости от статуса подключения COM
        self.com_connect_btn.setText("Отключить" if self.is_serial_connected else "Подключить")
        self.com_port_combo.setEnabled(not self.is_serial_connected)
        # self.reconnect_button.setEnabled(False) # Кнопка Bluetooth удалена

    # Слот для обработки уведомлений в основном потоке (если нужно обновить UI)
    def _handle_button_press_ui(self, button_id_from_device):
        print(f"Получен ID кнопки от устройства: {button_id_from_device}")

        # --- Слой трансляции ID (новая логика) ---
        target_page_name = None
        target_local_id = None

        if not isinstance(button_id_from_device, int) or button_id_from_device < 11:
            print(f"Ошибка: Получен некорректный ID кнопки от устройства: {button_id_from_device}")
            return

        page_digit = button_id_from_device // 10 # Получаем первую цифру (1, 2 или 3)
        target_local_id = button_id_from_device % 10 # Получаем вторую цифру (1-9)

        if target_local_id == 0 or target_local_id > 9 : # Проверка корректности локального ID
             print(f"Ошибка: Некорректный локальный ID ({target_local_id}) в ID от устройства: {button_id_from_device}")
             return

        if page_digit == 1:
            target_page_name = 'game'
        elif page_digit == 2:
            target_page_name = 'main'
        elif page_digit == 3:
            target_page_name = 'chill'
        else:
            print(f"Ошибка: Неизвестный идентификатор страницы ({page_digit}) в ID от устройства: {button_id_from_device}")
            return

        print(f"Сопоставлено с: Страница='{target_page_name}', Локальный ID={target_local_id}")
        # --- Конец слоя трансляции ---

        # Получаем актуальную конфигурацию для кнопки, используя транслированные значения
        # Используем .get(target_page_name, {}) для безопасности, если страница не найдена в конфиге
        config = self.page_configs.get(target_page_name, {}).get(target_local_id)

        if not config:
             # Используем локальный ID и имя страницы для сообщения об ошибке
             print(f"Нет конфигурации для кнопки с локальным ID {target_local_id} на странице '{target_page_name}' (устройство прислало {button_id_from_device})")
             # Можно не выходить, если сервисные кнопки не требуют конфига
             # return

        key_combo = config.get('combo') if config else None # Получаем combo, если конфиг есть

        # --- Логика выполнения действия ---
        # Используем target_local_id для определения типа кнопки (1-6 или 7-9)

        is_service_button = target_local_id in [7, 8, 9]

        if key_combo and not is_service_button: # Если есть комбинация и это НЕ сервисная кнопка 7,8,9
            print(f"Эмуляция действия для кнопки {target_local_id} на стр. '{target_page_name}' ({key_combo})")
            try:
                keyboard.send(key_combo)
            except Exception as e:
                 print(f"Ошибка keyboard.send для {key_combo}: {e}")
        elif not key_combo and not is_service_button: # Если нет комбинации и это НЕ сервисная кнопка 7,8,9
             print(f"Нет комбинации клавиш для кнопки {target_local_id} на стр. '{target_page_name}'")
        elif is_service_button: # Обработка сервисных кнопок (локальные ID 7, 8, 9)
            if target_local_id == 7: # Переключение НАЗАД
                print(f"Действие для сервисной кнопки {target_local_id} (ID устр: {button_id_from_device}): Переход НАЗАД")
                # TODO: Реализовать логику перехода на предыдущую страницу в UI компаньона
                # Например:
                # page_order = ['game', 'main', 'chill'] # Определите ваш порядок
                # try:
                #     current_index = page_order.index(self.current_page_name)
                #     prev_index = (current_index - 1 + len(page_order)) % len(page_order)
                #     self._switch_page(page_order[prev_index])
                # except ValueError:
                #     print("Ошибка: Текущая страница не найдена в порядке страниц")
                # Код выше может потребовать отправки команды обратно на устройство, чтобы оно тоже сменило экран

            elif target_local_id == 8: # Смена аудио
                print(f"Действие для сервисной кнопки {target_local_id} (ID устр: {button_id_from_device}): Переключение аудио")
                # TODO: Добавить вызов функции переключения аудиоустройств, если она есть
                # Если для этой кнопки тоже есть 'combo' в config.json, его можно выполнить:
                if key_combo:
                    print(f"Выполняется 'combo' для сервисной кнопки 8: {key_combo}")
                    try: keyboard.send(key_combo)
                    except Exception as e: print(f"Ошибка keyboard.send для сервисной кнопки 8 ({key_combo}): {e}")

            elif target_local_id == 9: # Переключение ВПЕРЕД
                print(f"Действие для сервисной кнопки {target_local_id} (ID устр: {button_id_from_device}): Переход ВПЕРЕД")
                # TODO: Реализовать логику перехода на следующую страницу в UI компаньона
                # Например:
                # page_order = ['game', 'main', 'chill'] # Определите ваш порядок
                # try:
                #     current_index = page_order.index(self.current_page_name)
                #     next_index = (current_index + 1) % len(page_order)
                #     self._switch_page(page_order[next_index])
                # except ValueError:
                #     print("Ошибка: Текущая страница не найдена в порядке страниц")
                # Код выше может потребовать отправки команды обратно на устройство

        else: # Прочие случаи (маловероятно)
             print(f"Неизвестное состояние для кнопки {target_local_id} на стр. '{target_page_name}'")

    def closeEvent(self, event):
        """Переопределено для сворачивания в трей вместо выхода."""
        if self._force_quit: # Если выход инициирован из меню трея
            print("Принудительный выход...")
            # --- Корректное завершение COM-порта ПЕРЕД выходом --- 
            if self.is_serial_connected:
                 print("Остановка потока и закрытие COM-порта перед выходом...")
                 self._stop_serial_thread.set()
                 if self.serial_thread:
                     self.serial_thread.join(timeout=1)
                 if self.serial_port and self.serial_port.is_open:
                     self.serial_port.close()
                 self.is_serial_connected = False
                 print("COM-порт закрыт.")
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
                 # Опционально: показать уведомление о сворачивании
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
             'last_com_port': self.last_com_port,
             'minimize_on_startup': self.minimize_on_startup # Добавляем сохранение флага
         }
         try:
             with open(filename, 'w', encoding='utf-8') as f:
                 # Записываем объединенный словарь в файл
                 json.dump(config_to_save, f, indent=4, ensure_ascii=False)
             print(f"Конфигурация успешно сохранена в '{filename}'.")
         except IOError as e:
             print(f"Ошибка ввода/вывода при сохранении конфигурации в '{filename}': {e}")

    def _load_config(self, filename="config.json"):
        """Загружает конфигурацию кнопок и последний COM-порт из JSON-файла."""
        if not os.path.exists(filename):
            print(f"Файл конфигурации '{filename}' не найден. Используется конфигурация по умолчанию.")
            # Убедимся, что last_com_port тоже None по умолчанию
            self.last_com_port = None
            self.minimize_on_startup = False # По умолчанию
            return

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)

            # --- Проверяем, старый ли это формат или новый --- 
            if isinstance(loaded_data, dict) and 'button_configs' in loaded_data: # Новый или промежуточный формат
                loaded_configs = loaded_data['button_configs']
                # Загружаем порт, если он есть
                self.last_com_port = loaded_data.get('last_com_port') 
                # Загружаем флаг сворачивания, если он есть, иначе по умолчанию False
                self.minimize_on_startup = loaded_data.get('minimize_on_startup', False) 
                print(f"Загружен последний COM-порт: {self.last_com_port}")
                print(f"Загружена настройка сворачивания при запуске: {self.minimize_on_startup}")
            elif isinstance(loaded_data, dict) and 'main' in loaded_data: # Похоже на самый старый формат
                 # --- Старый формат (только page_configs) --- 
                 print("Обнаружен старый формат config.json. Загружаются только настройки кнопок.")
                 loaded_configs = loaded_data
                 self.last_com_port = None
                 self.minimize_on_startup = False # По умолчанию для старого формата
            else:
                print(f"Ошибка: Неизвестный формат файла конфигурации '{filename}'. Используется конфигурация по умолчанию.")
                self.page_configs = self._get_default_page_configs()
                self.last_com_port = None
                self.minimize_on_startup = False # По умолчанию
                return
            # ---------------------------------------------------------------------------

            # --- Валидация загруженной конфигурации КНОПОК --- 
            # ... (остальная часть функции валидации остается прежней, работает с loaded_configs) ...
            required_pages = {'main', 'game', 'chill'}
            if not isinstance(loaded_configs, dict) or not required_pages.issubset(loaded_configs.keys()):
                print(f"Ошибка: Секция 'button_configs' в '{filename}' имеет неверную структуру страниц. Используется конфигурация кнопок по умолчанию.")
                self.page_configs = self._get_default_page_configs()
                # self.last_com_port уже загружен (или None), не меняем его здесь
                return

            valid_config = True
            temp_validated_configs = self._get_default_page_configs() # Начнем с дефолта на случай ошибок

            for page_name, page_data in loaded_configs.items():
                if page_name not in required_pages: continue
                if not isinstance(page_data, dict):
                    valid_config = False; break
                # Сразу записываем в валидную структуру, чтобы не потерять целые страницы
                temp_validated_configs[page_name] = {} 
                for btn_id in range(1, 10):
                    btn_id_str = str(btn_id)
                    config = None
                    if btn_id_str in page_data:
                         config = page_data[btn_id_str]
                    elif btn_id in page_data:
                         config = page_data[btn_id]
                    
                    # Если кнопка есть в конфиге и она валидна
                    if config and isinstance(config, dict) and 'combo' in config and 'icon_path' in config:
                        temp_validated_configs[page_name][btn_id] = config
                    else:
                        # Если кнопки нет или она невалидна, берем дефолтное значение
                        print(f"Предупреждение: Некорректные или отсутствующие данные для кнопки {btn_id} на странице '{page_name}'. Используется значение по умолчанию.")
                        temp_validated_configs[page_name][btn_id] = {'combo': None, 'icon_path': None}
                        # Не прерываем валидацию из-за одной кнопки, просто используем дефолт
                        # valid_config = False; break 
                # if not valid_config: break # Не нужно, если мы не прерываем из-за кнопки

            # if not valid_config: # Условие может быть лишним, если мы всегда заполняем из дефолта
            #     print(f"Ошибка: Файл '{filename}' содержит неверную структуру кнопок. Используется конфигурация по умолчанию.")
            #     self.page_configs = self._get_default_page_configs()
            #     return
            
            # Присваиваем собранную конфигурацию
            self.page_configs = temp_validated_configs
            print(f"Конфигурация кнопок успешно загружена из '{filename}'.")

        except FileNotFoundError:
             print(f"Файл конфигурации '{filename}' не найден (повторно). Используется конфигурация по умолчанию.")
             self.page_configs = self._get_default_page_configs()
             self.last_com_port = None
             self.minimize_on_startup = False # По умолчанию
        except json.JSONDecodeError:
            print(f"Ошибка: Не удалось декодировать JSON из файла '{filename}'. Файл может быть поврежден. Используется конфигурация по умолчанию.")
            self.page_configs = self._get_default_page_configs()
            self.last_com_port = None
            self.minimize_on_startup = False # По умолчанию
        except Exception as e:
            print(f"Непредвиденная ошибка при загрузке конфигурации из '{filename}': {e}. Используется конфигурация по умолчанию.")
            self.page_configs = self._get_default_page_configs()
            self.last_com_port = None
            self.minimize_on_startup = False # По умолчанию

    # Вспомогательный метод для получения дефолтной конфигурации
    def _get_default_page_configs(self):
         return {
            'main': { i: {'combo': None, 'icon_path': None} for i in range(1, 10) },
            'game': { i: {'combo': None, 'icon_path': None} for i in range(1, 10) },
            'chill': { i: {'combo': None, 'icon_path': None} for i in range(1, 10) }
        }

    # --- Методы для работы с треем --- 
    def _setup_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("Системный трей недоступен.")
            return

        icon_path = "icon.png" # Укажите путь к вашей иконке
        if not os.path.exists(icon_path):
             print(f"Предупреждение: Файл иконки '{icon_path}' не найден. Иконка в трее не будет установлена.")
             # Можно использовать стандартную иконку приложения, если она задана
             # self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
             # Или просто выйти
             return 
        
        self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
        self.tray_icon.setToolTip("Stream Deck Companion")

        # Создаем меню
        tray_menu = QMenu()
        show_action = QAction("Показать", self)
        quit_action = QAction("Выход", self)

        # Подключаем действия
        show_action.triggered.connect(self.show_normal)
        quit_action.triggered.connect(self._quit_application)

        # Добавляем действия в меню
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        # Устанавливаем меню для иконки
        self.tray_icon.setContextMenu(tray_menu)

        # Подключаем сигнал активации иконки
        self.tray_icon.activated.connect(self._tray_icon_activated)

        # Показываем иконку
        self.tray_icon.show()
        print("Иконка в трее успешно создана и показана.")

    def show_normal(self):
        """Показывает окно из трея."""
        self.show()
        self.activateWindow() # Делает окно активным
        self.raise_() # Поднимает окно поверх других

    def _quit_application(self):
        """Инициирует корректный выход из приложения."""
        print("Получена команда выхода из трея...")
        self._force_quit = True
        self.close() # Вызовет closeEvent, который теперь пропустит выход
        QApplication.instance().quit() # Добавляем явный выход

    def _tray_icon_activated(self, reason):
        """Обрабатывает клики по иконке трея."""
        # Показываем окно по двойному клику
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_normal()
        # Можно добавить обработку одинарного клика, если нужно
        # elif reason == QSystemTrayIcon.ActivationReason.Trigger:
        #     self.show_normal()

# Используем стандартный запуск QApplication
def main():
    app = QApplication(sys.argv)
    
    # loop = qasync.QEventLoop(app) # Убрано
    # asyncio.set_event_loop(loop) # Убрано
    
    window = StreamDeckCompanion()
    window.show()
    
    # Автоматически скрываем окно в трей через 100 мс после показа
    # Это нужно, чтобы окно успело инициализироваться перед скрытием
    #QTimer.singleShot(100, window.hide)

    # with loop: # Убрано
    #     loop.run_forever() # Убрано
    sys.exit(app.exec()) # Стандартный запуск цикла событий PyQt

if __name__ == '__main__':
    main() 