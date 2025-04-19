import keyboard
import serial
import serial.tools.list_ports
import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal

def handle_button_action(button_id_from_device, page_configs, current_page_name, switch_page_callback=None):
    """Обрабатывает нажатие кнопки, полученное от устройства.

    Args:
        button_id_from_device (int): ID кнопки, полученный от устройства (например, 11, 23, 39).
        page_configs (dict): Словарь конфигураций всех страниц.
        current_page_name (str): Имя текущей активной страницы в GUI.
        switch_page_callback (function, optional): Функция для переключения страницы в GUI. 
                                                    Принимает имя новой страницы.
    """
    print(f"Обработка действия для ID кнопки от устройства: {button_id_from_device}")

    # --- Слой трансляции ID --- 
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

    # Определяем страницу по первой цифре ID
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

    # Получаем актуальную конфигурацию для кнопки
    config = page_configs.get(target_page_name, {}).get(target_local_id)

    if not config:
         print(f"Нет конфигурации для кнопки с локальным ID {target_local_id} на странице '{target_page_name}' (устройство прислало {button_id_from_device})")
         # Не выходим, т.к. сервисные кнопки могут не иметь конфига

    key_combo = config.get('combo') if config else None # Получаем combo, если конфиг есть

    # --- Логика выполнения действия ---
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
            if switch_page_callback:
                page_order = ['game', 'main', 'chill'] # Определите ваш порядок
                try:
                    current_index = page_order.index(current_page_name)
                    prev_index = (current_index - 1 + len(page_order)) % len(page_order)
                    print(f"Переключение UI на страницу: {page_order[prev_index]}")
                    switch_page_callback(page_order[prev_index])
                    # TODO: Отправить команду на устройство для смены экрана?
                except ValueError:
                    print("Ошибка: Текущая страница не найдена в порядке страниц")
            else:
                 print("Нет коллбэка для переключения страницы UI.")

        elif target_local_id == 8: # Смена аудио (или другое действие)
            print(f"Действие для сервисной кнопки {target_local_id} (ID устр: {button_id_from_device}): Действие кнопки 8")
            if key_combo:
                print(f"Выполняется 'combo' для сервисной кнопки 8: {key_combo}")
                try: 
                    keyboard.send(key_combo)
                except Exception as e: 
                    print(f"Ошибка keyboard.send для сервисной кнопки 8 ({key_combo}): {e}")
            else:
                print("Нет 'combo' для сервисной кнопки 8.")
                # TODO: Добавить другую логику, если не используется combo (например, переключение аудиоустройства)

        elif target_local_id == 9: # Переключение ВПЕРЕД
            print(f"Действие для сервисной кнопки {target_local_id} (ID устр: {button_id_from_device}): Переход ВПЕРЕД")
            if switch_page_callback:
                page_order = ['game', 'main', 'chill'] # Определите ваш порядок
                try:
                    current_index = page_order.index(current_page_name)
                    next_index = (current_index + 1) % len(page_order)
                    print(f"Переключение UI на страницу: {page_order[next_index]}")
                    switch_page_callback(page_order[next_index])
                    # TODO: Отправить команду на устройство для смены экрана?
                except ValueError:
                    print("Ошибка: Текущая страница не найдена в порядке страниц")
            else:
                print("Нет коллбэка для переключения страницы UI.")

    else: # Прочие случаи (маловероятно)
         print(f"Неизвестное состояние для кнопки {target_local_id} на стр. '{target_page_name}'")

class ComManagerSignals(QObject):
    """Сигналы для ComManager."""
    # Сигнал обновления статуса: (message: str, is_connected: bool, port_name: str | None)
    status_updated = pyqtSignal(str, bool, object) 
    # Сигнал обновления списка портов: (ports: list[tuple[str, str]]) -> [(display_name, device_name)]
    port_list_updated = pyqtSignal(list)
    # Сигнал получения данных: (data: str)
    data_received = pyqtSignal(str)


class ComManager(QObject):
    """Управляет подключением и чтением данных с COM-порта."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = ComManagerSignals()
        self.serial_port = None
        self.read_thread = None
        self.stop_event = threading.Event()
        self.is_connected = False
        self.last_port_name = None # Имя последнего успешно подключенного порта
        self.available_ports = [] # Список доступных портов [(display_name, device_name), ...]

    def update_ports(self):
        """Сканирует доступные COM-порты и испускает сигнал port_list_updated."""
        print("ComManager: Обновление списка COM-портов...")
        self.available_ports = []
        try:
            ports = serial.tools.list_ports.comports()
            for port in ports:
                self.available_ports.append((f"{port.device} - {port.description}", port.device))
            print(f"ComManager: Найдено портов: {len(self.available_ports)}")
            self.signals.port_list_updated.emit(self.available_ports)
        except Exception as e:
            print(f"ComManager: Ошибка при сканировании портов: {e}")
            self.signals.status_updated.emit(f"Ошибка сканирования: {e}", False, None)
            self.signals.port_list_updated.emit([]) # Отправляем пустой список

    def connect(self, port_device):
        """Подключается к указанному COM-порту."""
        if self.is_connected:
            print("ComManager: Уже подключено.")
            return

        print(f"ComManager: Попытка подключения к {port_device}...")
        try:
            # 115200 - стандартная скорость для ESP32 в вашем .ino файле.
            self.serial_port = serial.Serial(port_device, 115200, timeout=1)
            time.sleep(2) # Даем время на инициализацию порта

            if self.serial_port.is_open:
                self.is_connected = True
                self.last_port_name = port_device # Сохраняем имя порта
                status_message = f"Подключено к {port_device}"
                print(f"ComManager: {status_message}")
                self.signals.status_updated.emit(status_message, True, port_device)

                # Запускаем поток для чтения данных
                self.stop_event.clear()
                self.read_thread = threading.Thread(target=self._read_thread_func, daemon=True)
                self.read_thread.start()
            else:
                status_message = f"Ошибка подключения к {port_device}"
                print(f"ComManager: {status_message}")
                self.signals.status_updated.emit(status_message, False, None)
                self.serial_port = None
                self.last_port_name = None

        except serial.SerialException as e:
            status_message = f"Ошибка COM: {e}"
            print(f"ComManager: Ошибка SerialException при подключении к {port_device}: {e}")
            self.signals.status_updated.emit(status_message, False, None)
            self.serial_port = None
            self.last_port_name = None
        except Exception as e:
            status_message = f"Неизвестная ошибка подключения"
            print(f"ComManager: Неизвестная ошибка при подключении к {port_device}: {e}")
            self.signals.status_updated.emit(status_message, False, None)
            self.serial_port = None
            self.last_port_name = None

    def disconnect(self):
        """Отключается от текущего COM-порта."""
        if not self.is_connected:
            print("ComManager: Уже отключено.")
            return

        print("ComManager: Отключение от COM-порта...")
        self.stop_event.set() # Сигнализируем потоку об остановке
        if self.read_thread:
            self.read_thread.join(timeout=1) # Ждем завершения потока
            if self.read_thread.is_alive():
                 print("ComManager: Поток чтения не завершился вовремя.")
            self.read_thread = None
            
        port_closed_msg = ""
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
                port_closed_msg = f"Порт {self.serial_port.port} закрыт."
                print(f"ComManager: {port_closed_msg}")
            except serial.SerialException as e:
                 port_closed_msg = f"Ошибка при закрытии порта: {e}"
                 print(f"ComManager: {port_closed_msg}")

        self.serial_port = None
        self.is_connected = False
        # Не сбрасываем self.last_port_name при отключении, он нужен для автоподключения
        # self.last_port_name = None 
        status_message = f"COM-порт отключен. {port_closed_msg}".strip()
        print(f"ComManager: {status_message}")
        self.signals.status_updated.emit(status_message, False, None)


    def _read_thread_func(self):
        """Функция потока для чтения данных из COM-порта."""
        print("ComManager: Поток чтения COM-порта запущен.")
        while not self.stop_event.is_set():
            if self.serial_port and self.serial_port.is_open:
                try:
                    if self.serial_port.in_waiting > 0:
                        line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                        if line:
                            # print(f"ComManager [Recv]: {line}") # Отладка - убрать?
                            self.signals.data_received.emit(line)
                    else:
                        time.sleep(0.05) # Небольшая пауза
                except serial.SerialException as e:
                    print(f"ComManager: Ошибка чтения из COM-порта: {e}")
                    self.signals.status_updated.emit(f"Ошибка COM: {e}", False, None)
                    self.stop_event.set() # Останавливаем поток при ошибке
                    break
                except Exception as e:
                    print(f"ComManager: Неизвестная ошибка в потоке чтения COM: {e}")
                    self.signals.status_updated.emit("Критическая ошибка COM", False, None)
                    self.stop_event.set()
                    break
            else:
                 print("ComManager: COM-порт закрыт или недоступен в потоке чтения.")
                 self.stop_event.set()
                 break # Выход из цикла, если порт закрылся извне
        print("ComManager: Поток чтения COM-порта завершен.")

    def get_last_port_name(self):
        """Возвращает имя последнего успешно подключенного порта."""
        return self.last_port_name

    def set_last_port_name(self, port_name):
         """Устанавливает имя порта (используется при загрузке конфига)."""
         self.last_port_name = port_name

    def __del__(self):
        """Гарантирует отключение при удалении объекта."""
        if self.is_connected:
            print("ComManager: Вызов disconnect() из __del__.")
            self.disconnect()
