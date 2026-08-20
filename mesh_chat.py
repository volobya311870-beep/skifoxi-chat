import os
import time
import socket
import random
import uuid
from threading import Thread

# Защита графики для Windows (ANGLE) — необходима для стабильных тестов на ПК
os.environ['KIVY_GL_BACKEND'] = 'angle_sdl2'

from kivy.app import App
from kivy.core.window import Window
from kivy.properties import BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import Clock

# Программный мост к железным функциям Android (Wi-Fi P2P)
try:
    from jnius import autoclass
    Context = autoclass('android.content.Context')
    WifiP2pManager = autoclass('android.net.wifi.p2p.WifiP2pManager')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
except ImportError:
    WifiP2pManager = None
class MeshChatApp(App):
    radar_visible = BooleanProperty(False)
    
    # Твой секретный ключ для жесткой изоляции сети от внешнего шума
    NETWORK_SIGNATURE = "[SkiFoxi_V]"

    def build(self):
        # Защита интерфейса от перекрытия экранной клавиатурой на смартфонах
        Window.softinput_mode = 'pan'
        
        # Наш уникальный ID (паспорт устройства) и позывной в сети
        self.my_id = str(uuid.uuid4())[:8]
        self.my_name = "Мистер Скиф"

        # Тактические буферы памяти меш-сети
        self.active_peers = {}        # Данные узлов на радаре: {peer_id: {ip, name, signal, last_seen}}
        self.radar_buttons = {}       # Ссылки на графические кнопки: {peer_id: Кнопка}
        self.incoming_fragments = {}  # Селективная сборка: {msg_id: {'total': X, ...}}
        self.msg_buffer = {}          # Буфер переноса (транзит): {msg_id: {chunk_num: text}}
        self.delivered_ids = set()    # Список закрытых ID (защита от повторного заражения)
        # Сборка тактических слоев интерфейса
        self.main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        self.workspace = BoxLayout(orientation='horizontal', spacing=10)
        self.chat_layout = BoxLayout(orientation='vertical', spacing=10)
        
        # Кнопка управления Радаром
        toggle_button = Button(text="👥 Радар SkiFoxi", size_hint_y=None, height=45, background_color=(1, 0.5, 0, 1))
        toggle_button.bind(on_press=self.toggle_radar)
        self.main_layout.add_widget(toggle_button)
        
        # Главный терминал вывода сообщений
        self.chat_logs = TextInput(text="Система SkiFoxi активна, Сер. Вирусный меш-протокол взведен.\n", readonly=True, multiline=True)
        self.chat_layout.add_widget(self.chat_logs)
        # Поле ввода текста (Для теста формата отправки: "ID_ЦЕЛИ:Сообщение", например "abc12345:Привет")
        self.message_input = TextInput(hint_text="Формат: ID_ЦЕЛИ:Текст (например, 8:Привет)...", multiline=False, size_hint_y=None, height=50)
        self.chat_layout.add_widget(self.message_input)
        
        # Кнопка отправки текстовых пакетов
        send_button = Button(text="Запустить в эфир", size_hint_y=None, height=50, background_color=(0.1, 0.8, 0.1, 1))
        send_button.bind(on_press=self.send_message)
        self.chat_layout.add_widget(send_button)
        
        # Массивная кнопка Рации «Нажми и говори»
        walkie_button = Button(text="🎤 НАЖМИ И ГОВОРИ", size_hint_y=None, height=60, background_color=(0.8, 0.2, 0.2, 1))
        walkie_button.bind(on_touch_down=lambda inst, t: (self.start_voice(inst, t), True) if inst.collide_point(*t.pos) else False)
        walkie_button.bind(on_touch_up=lambda inst, t: (self.stop_voice(inst, t), True) if inst.collide_point(*t.pos) else False)
        self.chat_layout.add_widget(walkie_button)
        # Выдвижная правая панель Радара
        self.radar_layout = BoxLayout(orientation='vertical', size_hint_x=None, width=0)
        self.radar_scroll = ScrollView()
        self.radar_grid = GridLayout(cols=1, spacing=5, size_hint_y=None)
        self.radar_grid.bind(minimum_height=self.radar_grid.setter('height'))
        self.radar_scroll.add_widget(self.radar_grid)
        
        self.radar_layout.add_widget(Label(text="👥 УЗЛЫ СЕТИ", size_hint_y=None, height=30))
        self.radar_layout.add_widget(self.radar_scroll)
        
        # Окончательная стыковка
        self.workspace.add_widget(self.chat_layout)
        self.workspace.add_widget(self.radar_layout)
        self.main_layout.add_widget(self.workspace)
        
        # ТАКТИЧЕСКИЙ РЕВИЗОР: Каждые 5 секунд очищает эфир от пропавших узлов (тишина > 30 сек)
        Clock.schedule_interval(self.cleanup_missing_peers, 5)
        
        self.start_mesh_network()
        return self.main_layout
    def toggle_radar(self, instance):
        self.radar_visible = not self.radar_visible
        self.radar_layout.width = 250 if self.radar_visible else 0

    def send_message(self, instance):
        """Шинкует сообщение на микро-осколки и отправляет целенаправленно"""
        raw_text = self.message_input.text.strip()
        if raw_text and ":" in raw_text:
            try:
                target_id, message_text = raw_text.split(":", 1)
                msg_id = f"MSG_{random.randint(1000, 9999)}"
                broadcast_addr = ('255.255.255.255', 50001)
                
                # Шинкуем текст на ультра-мелкие куски по 32 символа для высокой пробиваемости
                chunk_size = 32
                chunks = [message_text[i:i+chunk_size] for i in range(0, len(message_text), chunk_size)]
                total_chunks = len(chunks)
                # Кладем все части в свой буфер переноса (мы ведь тоже переносчик первой волны)
                if msg_id not in self.msg_buffer:
                    self.msg_buffer[msg_id] = {}
                
                for index, chunk in enumerate(chunks):
                    chunk_num = index + 1
                    # Сохраняем структуру
                    self.msg_buffer[msg_id][chunk_num] = {
                        'text': chunk, 'sender': self.my_name, 'target': target_id, 'total': total_chunks
                    }
                    
                    # Стреляем первой волной в эфир
                    packet_data = f"{self.NETWORK_SIGNATURE}DATA:{msg_id}:{chunk_num}:{total_chunks}:{self.my_name}:{target_id}|{chunk}"
                    self.mesh_socket.sendto(packet_data.encode('utf-8'), broadcast_addr)
                    time.sleep(0.005) # Пауза 5мс, чтобы чип не захлебнулся
                
                self.chat_logs.text += f"Вы [для Тел {target_id}]: {message_text} (Запущено в меш-цепь)\n"
                self.message_input.text = ""
            except Exception as e:
                self.chat_logs.text += f"Ошибка инициализации меш-пакета: {e}\n"

    def start_voice(self, instance, touch):
        self.start_time = time.time()
        self.chat_logs.text += "Рация: Запись звука...\n"

    def stop_voice(self, instance, touch):
        if hasattr(self, 'start_time') and self.start_time > 0:
            duration = round(time.time() - self.start_time, 1)
            self.chat_logs.text += f"Рация: Голосовое ушло ({duration} сек.)\n"
            self.start_time = 0
    def start_mesh_network(self):
        try:
            self.mesh_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.mesh_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.mesh_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.mesh_socket.settimeout(1.0)
            self.mesh_socket.bind(('', 50001))
            
            self.network_thread = Thread(target=self.listen_network, daemon=True)
            self.network_thread.start()
            
            self.beacon_thread = Thread(target=self.send_beacon, daemon=True)
            self.beacon_thread.start()
            
            if WifiP2pManager is not None:
                self.init_wifi_direct_hardware()
            else:
                self.chat_logs.text += "Система: Режим ПК. Маяк и сканирование запущены в эмуляции.\n"
        except Exception as e:
            self.chat_logs.text += f"Ошибка сети: {e}\n"

    def init_wifi_direct_hardware(self):
        try:
            activity = PythonActivity.mActivity
            self.p2p_manager = activity.getSystemService(Context.WIFI_P2P_SERVICE)
            self.p2p_channel = self.p2p_manager.initialize(activity, activity.getMainLooper(), None)
            self.p2p_manager.discoverPeers(self.p2p_channel, None)
            self.chat_logs.text += "Радар: Встроенный Wi-Fi датчик переведен в режим прямого P2P сканирования.\n"
        except Exception as e:
            self.chat_logs.text += f"Внимание, Сер: Аппаратный перехват чипа недоступен: {str(e)}\n"
    def send_beacon(self):
        """Маяк транслирует чек-лист имеющихся осколков, чтобы не принимать дубликаты"""
        while True:
            try:
                checklist = []
                # Опрашиваем буфер сборки (для сообщений, которые идут НАМ)
                for msg_id, info in self.incoming_fragments.items():
                    have_parts = ",".join(map(str, info['parts'].keys()))
                    checklist.append(f"{msg_id}:{have_parts}")
                
                status_str = "|".join(checklist) if checklist else "EMPTY"
                beacon_data = f"{self.NETWORK_SIGNATURE}INFO:{self.my_id}:{self.my_name}:{status_str}"
                self.mesh_socket.sendto(beacon_data.encode('utf-8'), ('255.255.255.255', 50001))
            except:
                pass
            time.sleep(4)

    def listen_network(self):
        while True:
            try:
                data, addr = self.mesh_socket.recvfrom(2048)
                if data:
                    raw_msg = data.decode('utf-8', errors='ignore')
                    if raw_msg.startswith(self.NETWORK_SIGNATURE):
                        clean_msg = raw_msg.replace(self.NETWORK_SIGNATURE, "", 1)
                        peer_ip = addr  # Изолируем чистый IP

                        # --- 1. ОБРАБОТКА РУКОПОЖАТИЯ (INFO) ---
                        if clean_msg.startswith("INFO:"):
                            meta = clean_msg.replace("INFO:", "", 1)
                            sender_id, sender_name, peer_status = meta.split(':', 2)
                            
                            # Обновляем радар при каждом получении INFO-пакета
                            fake_dbm = random.randint(-90, -40)
                            Clock.schedule_once(lambda dt, p_id=sender_id, p_name=sender_name, ip=peer_ip, dbm=fake_dbm: self.update_radar(p_id, p_name, ip, dbm))
                            # Селективный обмен: проверяем, какие из наших транзитных кусков нужны соседу
                            if peer_status != "EMPTY" and ":" in peer_status:
                                messages_on_peer = peer_status.split('|')
                                for msg_data in messages_on_peer:
                                    if ":" not in msg_data: continue
                                    m_id, parts_str = msg_data.split(':', 1)
                                    peer_has_parts = set(map(int, parts_str.split(','))) if parts_str else set()
                                    
                                    if m_id in self.msg_buffer:
                                        our_parts = set(self.msg_buffer[m_id].keys())
                                        # ХИРУРГИЧЕСКИЙ ФИЛЬТР: Отправляем только те части, которых у НЕГО НЕТ
                                        missing_parts = our_parts - peer_has_parts
                                        for chunk_num in missing_parts:
                                            self.transfer_specific_chunk(m_id, chunk_num, peer_ip)
                        # --- 2. ПРИЕМ ОСКОЛКА ДАННЫХ (DATA) ---
                        elif clean_msg.startswith("DATA:"):
                            meta, chunk_text = clean_msg.replace("DATA:", "", 1).split('|', 1)
                            m_id, c_num, t_chunks, sender, target = meta.split(':')
                            c_num, t_chunks = int(c_num), int(t_chunks)
                            
                            if m_id in self.delivered_ids: continue
                            
                            # ЕСЛИ МЫ ЦЕЛЬ (Телефон 8 / Мистер Скиф)
                            if self.my_id == target or target == "8":
                                if m_id not in self.incoming_fragments:
                                    self.incoming_fragments[m_id] = {'total': t_chunks, 'parts': {}, 'sender': sender}
                                
                                # ЖЕСТКИЙ ЗАПРЕТ ДУБЛИКАТОВ: если осколок уже есть — сброс пакета!
                                if c_num in self.incoming_fragments[m_id]['parts']:
                                    continue
                                    
                                self.incoming_fragments[m_id]['parts'][c_num] = chunk_text
                                # Если мозаика собрана на 100%
                                if len(self.incoming_fragments[m_id]['parts']) == t_chunks:
                                    full_msg = "".join([self.incoming_fragments[m_id]['parts'][i] for i in range(1, t_chunks + 1)])
                                    Clock.schedule_once(lambda dt, m=full_msg, s=sender: self._add_to_chat(m, s))
                                    del self.incoming_fragments[m_id]
                                    self.activate_kill_switch(m_id)
                            else:
                                # Мы транзитный узел: сохраняем осколок для дальнейшего переноса
                                if m_id not in self.msg_buffer:
                                    self.msg_buffer[m_id] = {}
                                self.msg_buffer[m_id][c_num] = {
                                    'text': chunk_text, 'sender': sender, 'target': target, 'total': t_chunks
                                }

                        # --- 3. ПРИКАЗ ОБ УНИЧТОЖЕНИИ (KILL-SWITCH) ---
                        elif clean_msg.startswith("KILL:"):
                            m_id = clean_msg.replace("KILL:", "", 1)
                            if m_id in self.msg_buffer: del self.msg_buffer[m_id]
                            if m_id in self.incoming_fragments: del self.incoming_fragments[m_id]
                            self.delivered_ids.add(m_id)
                            # Эхо-ретрансляция приказа дальше по цепочке
                            self.mesh_socket.sendto(f"{self.NETWORK_SIGNATURE}KILL:{m_id}".encode('utf-8'), ('255.255.255.255', 50001))

            except socket.timeout: continue
            except: break
    def transfer_specific_chunk(self, msg_id, chunk_num, peer_ip):
        try:
            info = self.msg_buffer[msg_id][chunk_num]
            # Собираем точечный пакет данных для конкретного узла
            packet = f"{self.NETWORK_SIGNATURE}DATA:{msg_id}:{chunk_num}:{info['total']}:{info['sender']}:{info['target']}|{info['text']}"
            self.mesh_socket.sendto(packet.encode('utf-8'), (peer_ip[0], 50001))
        except:
            pass

    def activate_kill_switch(self, msg_id):
        self.delivered_ids.add(msg_id)
        kill_packet = f"{self.NETWORK_SIGNATURE}KILL:{msg_id}"
        # Повторяем импульс 3 раза для пробития лесных помех
        for _ in range(3):
            self.mesh_socket.sendto(kill_packet.encode('utf-8'), ('255.255.255.255', 50001))
            time.sleep(0.05)

    def get_signal_bars(self, dbm_level):
        """Конвертер мощности радиоволн в графическую шкалу"""
        if dbm_level >= -50: return "[|||||]", (0.1, 0.8, 0.1, 1)
        elif dbm_level >= -65: return "[|||| ]", (0.2, 0.7, 0.2, 1)
        elif dbm_level >= -75: return "[|||  ]", (0.9, 0.7, 0.1, 1)
        elif dbm_level >= -85: return "[||   ]", (1, 0.5, 0, 1)
        else: return "[|    ]", (0.9, 0.1, 0.1, 1)
    def update_radar(self, peer_id, peer_name, peer_ip, current_dbm):
        """Интеллектуальное ведение картотеки Радара без дублирования контактов"""
        try:
            bars, btn_color = self.get_signal_bars(current_dbm)
            button_text = f"🦊 {peer_name} ({peer_id}) {bars}"
            
            if peer_id in self.active_peers:
                self.active_peers[peer_id]['ip'] = peer_ip
                self.active_peers[peer_id]['last_seen'] = time.time()
                self.active_peers[peer_id]['signal'] = current_dbm
                Clock.schedule_once(lambda dt: self._refresh_button_ui(peer_id, button_text, btn_color))
            else:
                self.active_peers[peer_id] = {
                    'ip': peer_ip, 'name': peer_name, 'last_seen': time.time(), 'signal': current_dbm
                }
                Clock.schedule_once(lambda dt: self._create_button_ui(peer_id, button_text, btn_color))
                self.chat_logs.text += f"Радар: [{peer_name}] ({peer_id}) вошел в круг.\n"
        except:
            pass

    def _create_button_ui(self, peer_id, btn_text, btn_color):
        new_contact = Button(text=btn_text, size_hint_y=None, height=45, background_color=btn_color)
        self.radar_buttons[peer_id] = new_contact
        self.radar_grid.add_widget(new_contact)

    def _refresh_button_ui(self, peer_id, btn_text, btn_color):
        if peer_id in self.radar_buttons:
            self.radar_buttons[peer_id].text = btn_text
            self.radar_buttons[peer_id].background_color = btn_color

    def cleanup_missing_peers(self, dt):
        """Фоновая зачистка Радара от потерянных Скиф-узлов (тишина > 30 сек)"""
        current_time = time.time()
        peers_to_remove = [p_id for p_id, info in self.active_peers.items() if (current_time - info['last_seen']) > 30]
        
        for peer_id in peers_to_remove:
            peer_name = self.active_peers[peer_id]['name']
            if peer_id in self.radar_buttons:
                self.radar_grid.remove_widget(self.radar_buttons[peer_id])
                del self.radar_buttons[peer_id]
            del self.active_peers[peer_id]
            self.chat_logs.text += f"Радар: Связь с [{peer_name}] потеряна. Узел удален.\n"

    def _add_to_chat(self, msg, sender_name):
        self.chat_logs.text += f"[{sender_name}]: {msg}\n"

    def on_stop(self):
        if hasattr(self, 'mesh_socket'):
            self.mesh_socket.close()


if __name__ == "__main__":
    MeshChatApp().run()
