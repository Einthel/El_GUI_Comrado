import json
import os
from pathlib import Path

class ConfigManager:
    def __init__(self):
        self.config_dir = Path.home() / '.streamdeck_companion'
        self.config_file = self.config_dir / 'config.json'
        self.default_config = {
            'buttons': {
                'fan_1': {'action': 'fan1', 'icon': 'fan_ico.png', 'hotkey': 'ctrl+1'},
                'fan_2': {'action': 'fan2', 'icon': 'fan_ico.png', 'hotkey': 'ctrl+2'},
                'fan_3': {'action': 'fan3', 'icon': 'fan_ico.png', 'hotkey': 'ctrl+3'},
                'shot_4': {'action': 'shot', 'icon': 'shot_ico.png', 'hotkey': 'ctrl+4'},
                'video_5': {'action': 'video', 'icon': 'play_ico.png', 'hotkey': 'ctrl+5'},
                'ovrl_6': {'action': 'ovrl', 'icon': 'ovr_ico.png', 'hotkey': 'ctrl+6'}
            },
            'theme': 'default',
            'settings': {
                'bluetooth_name': 'Stream Deck',
                'bluetooth_password': '1234',
                'screen_brightness': 80
            }
        }
        self.load_config()
    
    def load_config(self):
        """Загрузка конфигурации из файла"""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True)
            
        if not self.config_file.exists():
            self.save_config(self.default_config)
            self.config = self.default_config
        else:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
    
    def save_config(self, config):
        """Сохранение конфигурации в файл"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    
    def update_button_config(self, button_id, new_config):
        """Обновление конфигурации кнопки"""
        if button_id in self.config['buttons']:
            self.config['buttons'][button_id].update(new_config)
            self.save_config(self.config)
    
    def update_theme(self, theme_name):
        """Обновление текущей темы"""
        self.config['theme'] = theme_name
        self.save_config(self.config)
    
    def update_settings(self, new_settings):
        """Обновление общих настроек"""
        self.config['settings'].update(new_settings)
        self.save_config(self.config) 