import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import pyaudio
import socket
import threading
import cv2
import pyautogui
import numpy as np
from PIL import Image, ImageTk
import pickle
import struct
import platform
if platform.system() != 'Windows':
    from xvfbwrapper import Xvfb

# Classes for Audio, Screen and Camera Streaming
class AudioSender:

    def __init__(self, host, port, audio_format=pyaudio.paInt16, channels=1, rate=44100, frame_chunk=4096):
        self.__host = host
        self.__port = port

        self.__audio_format = audio_format
        self.__channels = channels
        self.__rate = rate
        self.__frame_chunk = frame_chunk

        self.__sending_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__audio = pyaudio.PyAudio()

        self.__running = False

    # def __callback(self, in_data, frame_count, time_info, status):
    #     if self.__running:
    #         self.__sending_socket.send(in_data)
    #         return (None, pyaudio.paContinue)
    #     else:
    #         try:
    #             self.__stream.stop_stream()
    #             self.__stream.close()
    #             self.__audio.terminate()
    #             self.__sending_socket.close()
    #         except OSError:
    #             pass # Dirty Solution For Now (Read Overflow)
    #         return (None, pyaudio.paComplete)

    def start_stream(self):
        if self.__running:
            print("Already streaming")
        else:
            self.__running = True
            thread = threading.Thread(target=self.__client_streaming)
            thread.start()

    def stop_stream(self):
        if self.__running:
            self.__running = False
            self.__sending_socket.close()
        else:
            print("Client not streaming")

    def __client_streaming(self):
        self.__sending_socket.connect((self.__host, self.__port))
        self.__stream = self.__audio.open(format=self.__audio_format, channels=self.__channels, rate=self.__rate,
                                          input=True, frames_per_buffer=self.__frame_chunk)
        while self.__running:
            self.__sending_socket.send(self.__stream.read(self.__frame_chunk))

        try:
            self.__sending_socket.connect((self.__host, self.__port))
            self.__stream = self.__audio.open(format=self.__audio_format, channels=self.__channels, rate=self.__rate,
                                              input=True, frames_per_buffer=self.__frame_chunk)
            while self.__running:
                self.__sending_socket.send(self.__stream.read(self.__frame_chunk))
        except Exception as e:
            print(f"Error in streaming: {e}")
        finally:
            self.__cleanup()

    def __cleanup(self):
        try:
            try:
                self.__stream.stop_stream()
                self.__stream.close()
            except Exception as e:
                print(f"Error closing stream: {e}")
            self.__audio.terminate()
            self.__sending_socket.close()
        except OSError:
            pass
        except Exception as e:
            print(f"Error in cleanup: {e}")

class AudioReceiver:

    def __init__(self, host, port, slots=8, audio_format=pyaudio.paInt16, channels=1, rate=44100, frame_chunk=4096):
        self.__host = host
        self.__port = port

        self.__slots = slots
        self.__used_slots = 0

        self.__audio_format = audio_format
        self.__channels = channels
        self.__rate = rate
        self.__frame_chunk = frame_chunk

        self.__audio = pyaudio.PyAudio()

        self.__server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__server_socket.bind((self.__host, self.__port))

        self.__block = threading.Lock()
        self.__running = False

    def start_server(self):
        if self.__running:
            print("Audio server is running already")
        else:
            self.__running = True
            # Have to figure out __stream error here :)
            self.__stream = self.__audio.open(format=self.__audio_format, channels=self.__channels, rate=self.__rate,
                                              output=True, frames_per_buffer=self.__frame_chunk)
            thread = threading.Thread(target=self.__server_listening)
            thread.start()

    def __server_listening(self):
        self.__server_socket.listen()
        while self.__running:
            self.__block.acquire()
            connection, address = self.__server_socket.accept()
            if self.__used_slots >= self.__slots:
                print("Connection refused! No free slots!")
                connection.close()
                self.__block.release()
                continue
            else:
                self.__used_slots += 1

            self.__block.release()
            thread = threading.Thread(target=self.__client_connection, args=(connection, address,))
            thread.start()

    def __client_connection(self, connection, address):
        while self.__running:
            try:
                data = connection.recv(self.__frame_chunk)
                if not data:
                    break
                self.__stream.write(data)
            except Exception as e:
                print(f"Error in client connection: {e}")
                break

    def stop_server(self):
        if self.__running:
            self.__running = False
            closing_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            closing_connection.connect((self.__host, self.__port))
            closing_connection.close()
            self.__block.acquire()
            self.__server_socket.close()
            self.__block.release()
            self.__cleanup()
        else:
            print("Server not running!")

    def __cleanup(self):
        try:
            self.__stream.stop_stream()
            self.__stream.close()
        except Exception as e:
            print(f"Error closing stream: {e}")
        self.__audio.terminate()

class StreamingServer:
    # TODO: Implement slots functionality
    def __init__(self, host, port, slots=8, quit_key='q'):
        self.__host = host
        self.__port = port
        self.__slots = slots
        self.__used_slots = 0
        self.__running = False
        self.__quit_key = quit_key
        self.__block = threading.Lock()
        self.__server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__init_socket()

    def __init_socket(self):
        self.__server_socket.bind((self.__host, self.__port))

    def start_server(self):
        if self.__running:
            print("Server is already running")
        else:
            self.__running = True
            server_thread = threading.Thread(target=self.__server_listening)
            server_thread.start()

    def __server_listening(self):
        self.__server_socket.listen()
        while self.__running:
            self.__block.acquire()
            connection, address = self.__server_socket.accept()
            if self.__used_slots >= self.__slots:
                print("Connection refused! No free slots!")
                connection.close()
                self.__block.release()
                continue
            else:
                self.__used_slots += 1
            self.__block.release()
            thread = threading.Thread(target=self.__client_connection, args=(connection, address,))
            thread.start()

    def stop_server(self):
        if self.__running:
            self.__running = False
            closing_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            closing_connection.connect((self.__host, self.__port))
            closing_connection.close()
            self.__block.acquire()
            self.__server_socket.close()
            self.__block.release()
        else:
            print("Server not running!")

    def __client_connection(self, connection, address):
        payload_size = struct.calcsize('>L')
        data = b""

        while self.__running:

            break_loop = False

            while len(data) < payload_size:
                received = connection.recv(4096)
                if received == b'':
                    connection.close()
                    self.__used_slots -= 1
                    break_loop = True
                    break
                data += received

            if break_loop:
                break

            packed_msg_size = data[:payload_size]
            data = data[payload_size:]

            msg_size = struct.unpack(">L", packed_msg_size)[0]

            while len(data) < msg_size:
                data += connection.recv(4096)

            frame_data = data[:msg_size]
            data = data[msg_size:]

            frame = pickle.loads(frame_data, fix_imports=True, encoding="bytes")
            frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)
            cv2.imshow(str(address), frame)
            if cv2.waitKey(1) == ord(self.__quit_key):
                connection.close()
                self.__used_slots -= 1
                break

class StreamingClient:
    def __init__(self, host, port):
        self.__host = host
        self.__port = port
        self._configure()
        self.__running = False
        self.__client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def _configure(self):
        self.__encoding_parameters = [int(cv2.IMWRITE_JPEG_QUALITY), 90]

    def _get_frame(self):
        return None

    def _cleanup(self):
        cv2.destroyAllWindows()

    def __client_streaming(self):
        try:
            self.__client_socket.connect((self.__host, self.__port))
            while self.__running:
                frame = self._get_frame()
                if frame is None:
                    continue
                result, frame = cv2.imencode('.jpg', frame, self.__encoding_parameters)
                data = pickle.dumps(frame, 0)
                size = len(data)

                try:
                    self.__client_socket.sendall(struct.pack('>L', size) + data)
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    self.__running = False
        except Exception as e:
            print(f"Error in client streaming: {e}")
        finally:
            self._cleanup()
            self.__client_socket.close()

    def start_stream(self):
        if self.__running:
            print("Client is already streaming!")
        else:
            self.__running = True
            client_thread = threading.Thread(target=self.__client_streaming)
            client_thread.start()

    def stop_stream(self):
        if self.__running:
            self.__running = False
        else:
            print("Client not streaming!")

class CameraClient(StreamingClient):
    def __init__(self, host, port, x_res=1280, y_res=800):
        self.__x_res = x_res
        self.__y_res = y_res
        self.__camera = cv2.VideoCapture(0)
        super(CameraClient, self).__init__(host, port)

    def _configure(self):
        self.__camera.set(3, self.__x_res)
        self.__camera.set(4, self.__y_res)
        super(CameraClient, self)._configure()

    def _get_frame(self):
        ret, frame = self.__camera.read()
        return frame

    def _cleanup(self):
        self.__camera.release()
        cv2.destroyAllWindows()

class VideoClient(StreamingClient):
    def __init__(self, host, port, video, loop=True):
        self.__video = cv2.VideoCapture(video)
        self.__loop = loop
        super(VideoClient, self).__init__(host, port)

    def _configure(self):
        self.__video.set(3, 1280)
        self.__video.set(4, 800)
        super(VideoClient, self)._configure()

    def _get_frame(self):
        ret, frame = self.__video.read()
        # modifications for looping
        if not ret and self.__loop:
            self.__video.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.__video.read()
        return frame

    def _cleanup(self):
        self.__video.release()
        cv2.destroyAllWindows()

class ScreenShareClient(StreamingClient):
    def __init__(self, host, port, x_res=1280, y_res=800):
        self.__x_res = x_res
        self.__y_res = y_res
        super(ScreenShareClient, self).__init__(host, port)

    def _get_frame(self):
        screen = pyautogui.screenshot()
        frame = np.array(screen)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.resize(frame, (self.__x_res, self.__y_res), interpolation=cv2.INTER_AREA)
        return frame

    def _cleanup(self):
        cv2.destroyAllWindows()

local_ip = socket.gethostbyname(socket.gethostname())
server = StreamingServer(local_ip, 9999)
receiver = AudioReceiver(local_ip, 5555)
# Initialize other necessary objects here

# Define global variables for threads and clients
t1 = None
t2 = None
t3 = None
t4 = None
t5 = None
camera_client = None
screen_client = None
audio_sender = None

# Define start functions
def start_listening():
    global t1, t2
    t1 = threading.Thread(target=server.start_server)
    t2 = threading.Thread(target=receiver.start_server)
    t1.start()
    t2.start()


def start_camera_stream():
    global t3, camera_client
    camera_client = CameraClient(text_target_ip.get(), 2345)
    t3 = threading.Thread(target=camera_client.start_stream)
    t3.start()


def start_screen_stream():
    global t4, screen_client
    if platform.system() == 'Windows':
        screen_client = ScreenShareClient(text_target_ip.get(), 2345)
        t4 = threading.Thread(target=screen_client.start_stream)
        t4.start()
    else:
        with Xvfb() as vdisplay:
            screen_client = ScreenShareClient(text_target_ip.get(), 2345)
            t4 = threading.Thread(target=screen_client.start_stream)
            t4.start()


def start_audio_stream():
    global t5, audio_sender
    audio_sender = AudioSender(text_target_ip.get(), 8080)
    t5 = threading.Thread(target=audio_sender.start_stream)
    t5.start()


# Define stop functions
def stop_listening():
    global t1, t2
    server.stop_server()
    receiver.stop_server()
    t1.join()
    t2.join()


def stop_camera_stream():
    global t3, camera_client
    camera_client.stop_stream()
    t3.join()


def stop_screen_stream():
    global t4, screen_client
    screen_client.stop_stream()
    t4.join()


def stop_audio_stream():
    global t5, audio_sender
    audio_sender.stop_stream()
    t5.join()


def copy_to_clipboard():
    window.clipboard_clear()
    window.clipboard_append(local_ip)
    window.update()


# GUI Setup and Configuration
window_main = tk.Tk()
window_main.title('Chit Chat')
window_main.geometry('1000x300')
window_main.config(bg='#cdc8e0')
window_main.resizable(False, False)
#window_main.iconbitmap('logo.ico')
#window_main.overrideredirect(True) # for no title bar
window = tk.Frame(window_main)
window.pack(expand=True, fill='both')
window.config(
    cursor='arrow',
    height=300,
    width=1000,
    bg='#282828',
    relief='ridge',
    borderwidth=1,
    border=0,
    highlightcolor='#282828',
    highlightthickness=0,
    takefocus=True,
)
#Making the window draggable (Grids)
window.rowconfigure(0, weight=1)
window.rowconfigure(1, weight=1)
window.rowconfigure(2, weight=1)
window.rowconfigure(3, weight=1)
window.rowconfigure(4, weight=1)
window.rowconfigure(5, weight=1)
window.columnconfigure(0, weight=1)
window.columnconfigure(1, weight=1)
window.columnconfigure(2, weight=1)
window.columnconfigure(3, weight=1)
window.columnconfigure(4, weight=1)
window.columnconfigure(5, weight=1)
# # # Buttons and Labels

# Label for target IP
label_show_ip = tk.Label(
    window,
    text='Your IP Address: ',
    font=('Times New Roman', 17, 'bold'),
    width=20,
    bg='#282828',
    fg='#bfc0c0',
    relief='flat',
    borderwidth=0,
)
label_show_ip.grid(row=2, column=2, sticky=tk.W + tk.E)
# Shows Device IP address
label_ip_address = tk.Label(
    window,
    text=local_ip,
    font=('Times New Roman', 16, 'bold','underline'),
    bg='#282828',
    fg='#bfc0c0',
    width=13,
    relief='flat',
    borderwidth=0,
)
label_ip_address.grid(row=2, column=3, sticky=tk.W + tk.E)
# Button to copy IP address to clipboard
#clipboard_img = ImageTk.PhotoImage(Image.open('copy.png').resize((20, 20)))
btn_copy_ip = tk.Button(
    window,
    text='Copy',
    #image=clipboard_img,
    width=5,
    font=('Times New Roman', 9),
    command=copy_to_clipboard
)
btn_copy_ip.grid(row=2, column=4, sticky=tk.W + tk.E)
# Label for target IP
label_target_ip = tk.Label(
    window,
    text='Target IP Address: ',
    font=('Times New Roman', 15),
    bg='#282828',
    fg='#bfc0c0',
    relief='flat',
    borderwidth=0,
)
label_target_ip.grid(row=3, column=2, sticky=tk.W + tk.E)
# Entry for target IP
text_target_ip = tk.Entry(
    window,
    width=10,
    font=('Times New Roman', 15),
    bg='#bfc0c0',
    fg='#282828',
    relief='flat',
    borderwidth=0,
)
text_target_ip.grid(row=3, column=3, sticky=tk.W + tk.E)
# Button to start Making the connection
btn_start = tk.Button(
    window,
    text='Connect',
    width=5,
    font=('Times New Roman', 15),
    command=start_listening
)
btn_start.grid(row=4, column=3, sticky=tk.W + tk.E)
# Button to stop Making the connection
def toggle_connect(event):
    if btn_start['text'] == 'Connect':
        btn_start.config(
            text='Stop',
            command=start_listening
        )
    else:
        btn_start.config(
            text='Connect',
            command=stop_listening
        )
# Binding the button to the function
btn_start.bind('<Button-1>', toggle_connect)
temp_btn = tk.Button(
    window,
    text='Temp',
    bg='#282828',
    borderwidth=0,
    fg='#282828',
    width=3,
    font=('Times New Roman', 15),
)
temp_btn.grid(row=10, column=1, sticky=tk.W + tk.E)
temp_btn_2 = tk.Button(
    window,
    text='Temp',
    bg='#282828',
    borderwidth=0,
    fg='#282828',
    width=3,
    font=('Times New Roman', 15),
)
temp_btn_2.grid(row=10, column=3, sticky=tk.W + tk.E)
temp_btn_3 = tk.Button(
    window,
    text='Functionalities',
    bg='#282828',
    borderwidth=0,
    fg='#bfc0c0',
    width=13,
    font=('Times New Roman', 17, 'underline', 'bold'),
)
temp_btn_3.grid(row=2, column=6, sticky=tk.W + tk.E)
temp_btn_4 = tk.Button(
    window,
    text='Temp',
    bg='#282828',
    borderwidth=0,
    fg='#282828',
    width=7,
    font=('Times New Roman', 15),
)
temp_btn_4.grid(row=10, column=7, sticky=tk.W + tk.E)
# Button to start Camera Share
btn_camera = tk.Button(
    window,
    text='Start Camera',
    width=20,
    font=('Times New Roman', 15),
    command=start_camera_stream
)
btn_camera.grid(row=3, column=6, sticky=tk.W + tk.E)
# Button to stop Camera Share
def toggle_camera_share(event):
    if btn_camera['text'] == 'Start Camera':
        btn_camera.config(
            text='Stop Camera',
            command=start_camera_stream
        )
    else:
        btn_camera.config(
            text='Start Camera',
            command=stop_camera_stream
        )
# Binding the button to the function
btn_camera.bind('<Button-1>', toggle_camera_share)
# Button to start Screen Share
btn_screen = tk.Button(
    window,
    text='Start Screen Share',
    width=20,
    font=('Times New Roman', 15),
    command=start_screen_stream
)
btn_screen.grid(row=4, column=6, sticky=tk.W + tk.E)
# Button to stop Screen Share
def toggle_screen_share(event):
    if btn_screen['text'] == 'Start Screen Share':
        btn_screen.config(
            text='Stop Screen Share',
            command=start_screen_stream
        )
    else:
        btn_screen.config(
            text='Start Screen Share',
            command=stop_screen_stream
        )
# Binding the button to the function
btn_screen.bind('<Button-1>', toggle_screen_share)
# Button to start Audio Share
btn_audio = tk.Button(
    window,
    text='Start Audio Share',
    width=20,
    font=('Times New Roman', 15),
    command=start_audio_stream
)
btn_audio.grid(row=5, column=6, sticky=tk.W + tk.E)
# Button to stop Audio Share
def toggle_audio_share(event):
    if btn_audio['text'] == 'Start Audio Share':
        btn_audio.config(
            text='Stop Audio Share',
            command=start_audio_stream
        )
    else:
        btn_audio.config(
            text='Start Audio Share',
            command=stop_audio_stream
        )
# Binding the button to the function
btn_audio.bind('<Button-1>', toggle_audio_share)

# Closing menu
def on_closing():
    if t1 is not None:
        stop_listening()
    if t3 is not None:
        stop_camera_stream()
    if t4 is not None:
        stop_screen_stream()
    if t5 is not None:
        stop_audio_stream()
    if messagebox.askokcancel("Quit", "Are you sure you want to quit?", icon='warning', parent=window, default='cancel', detail='All connections will be closed.'):
        window_main.destroy()
    window_main.destroy()

window_main.protocol("WM_DELETE_WINDOW", on_closing)

window.mainloop()