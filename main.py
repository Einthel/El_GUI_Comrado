import sys
from PyQt6.QtWidgets import QApplication


# Импортируем главный класс GUI из нового модуля
from GUI import StreamDeckCompanion



# Используем стандартный запуск QApplication
def main():
    app = QApplication(sys.argv)
    
   
    
    # Создаем экземпляр из импортированного класса
    window = StreamDeckCompanion()
    window.show()
    

    sys.exit(app.exec()) # Стандартный запуск цикла событий PyQt

if __name__ == '__main__':
    main() 
