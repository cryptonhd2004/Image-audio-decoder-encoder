#!/usr/bin/env python3
import json
import struct
import wave
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from PIL import Image


def image_to_channels(image_path: str):
    img = Image.open(image_path).convert('RGB')
    width, height = img.size
    r, g, b = img.split()
    return width, height, {
        'R': r.tobytes(),
        'G': g.tobytes(),
        'B': b.tobytes(),
    }


def bytes_to_samples(raw: bytes) -> bytes:
    samples = bytearray()
    for b in raw:
        s = (b - 128) << 8
        samples += struct.pack('<h', s)
    return bytes(samples)


def samples_to_bytes(frames: bytes) -> bytes:
    values = struct.unpack('<' + 'h' * (len(frames) // 2), frames)
    raw = bytearray()
    for s in values:
        b = max(0, min(255, (s >> 8) + 128))
        raw.append(b)
    return bytes(raw)


def write_mono_wav(payload: bytes, wav_path: str, sample_rate: int = 48000):
    samples = bytes_to_samples(payload)
    with wave.open(wav_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples)


def read_mono_wav(wav_path: str):
    with wave.open(wav_path, 'rb') as wf:
        params = wf.getparams()
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise ValueError(f'{wav_path}: očekávám mono 16-bit PCM WAV soubor.')
        frames = wf.readframes(wf.getnframes())
    return samples_to_bytes(frames), params


def save_meta(meta_path: str, width: int, height: int, sample_rate: int, prefix: str):
    meta = {
        'format': 'I2A_RGB_SPLIT_V1',
        'width': width,
        'height': height,
        'channels': ['R', 'G', 'B'],
        'sample_rate': sample_rate,
        'files': {
            'R': f'{prefix}_R.wav',
            'G': f'{prefix}_G.wav',
            'B': f'{prefix}_B.wav'
        }
    }
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)


def load_meta(meta_path: str) -> dict:
    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)
    if meta.get('format') != 'I2A_RGB_SPLIT_V1':
        raise ValueError('Neplatný meta.json formát.')
    required = {'width', 'height', 'files'}
    if not required.issubset(meta.keys()):
        raise ValueError('meta.json neobsahuje povinné položky.')
    return meta


def fit_payload(data: bytes, expected: int, mode: str) -> bytes:
    if len(data) == expected:
        return data
    if len(data) > expected:
        if mode in {'truncate', 'strict'}:
            return data[:expected]
        raise ValueError(f'Stopa je delší ({len(data)} B) než očekávaných {expected} B.')
    if len(data) < expected:
        if mode == 'pad':
            return data + bytes(expected - len(data))
        raise ValueError(f'Stopa je kratší ({len(data)} B) než očekávaných {expected} B.')
    return data


def encode_image(input_image: str, output_prefix: str, sample_rate: int = 48000):
    width, height, channels = image_to_channels(input_image)
    r_path = f'{output_prefix}_R.wav'
    g_path = f'{output_prefix}_G.wav'
    b_path = f'{output_prefix}_B.wav'
    meta_path = f'{output_prefix}_meta.json'
    write_mono_wav(channels['R'], r_path, sample_rate)
    write_mono_wav(channels['G'], g_path, sample_rate)
    write_mono_wav(channels['B'], b_path, sample_rate)
    save_meta(meta_path, width, height, sample_rate, output_prefix)
    return {
        'width': width,
        'height': height,
        'r_path': r_path,
        'g_path': g_path,
        'b_path': b_path,
        'meta_path': meta_path,
    }


def decode_image(r_wav: str, g_wav: str, b_wav: str, meta_json: str, output_image: str, fit_mode: str):
    meta = load_meta(meta_json)
    width = int(meta['width'])
    height = int(meta['height'])
    expected = width * height

    r_data, r_params = read_mono_wav(r_wav)
    g_data, g_params = read_mono_wav(g_wav)
    b_data, b_params = read_mono_wav(b_wav)

    r = fit_payload(r_data, expected, fit_mode)
    g = fit_payload(g_data, expected, fit_mode)
    b = fit_payload(b_data, expected, fit_mode)

    r_img = Image.frombytes('L', (width, height), r)
    g_img = Image.frombytes('L', (width, height), g)
    b_img = Image.frombytes('L', (width, height), b)

    img = Image.merge('RGB', (r_img, g_img, b_img))
    img.save(output_image)

    return {
        'width': width,
        'height': height,
        'expected': expected,
        'r_params': r_params,
        'g_params': g_params,
        'b_params': b_params,
        'output_image': output_image,
    }


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Image <-> Audio RGB GUI')
        self.geometry('900x720')
        self.minsize(820, 640)

        self.mode = tk.StringVar(value='encode')
        self.sample_rate = tk.StringVar(value='48000')
        self.fit_mode = tk.StringVar(value='truncate')

        self.input_image = tk.StringVar()
        self.output_prefix = tk.StringVar()

        self.r_wav = tk.StringVar()
        self.g_wav = tk.StringVar()
        self.b_wav = tk.StringVar()
        self.meta_json = tk.StringVar()
        self.output_image = tk.StringVar()

        self._build_ui()
        self._update_mode()

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill='both', expand=True)

        top = ttk.LabelFrame(root, text='Režim', padding=10)
        top.pack(fill='x')
        ttk.Radiobutton(top, text='Encode obrázek -> R/G/B WAV + meta.json', variable=self.mode, value='encode', command=self._update_mode).pack(anchor='w')
        ttk.Radiobutton(top, text='Decode R/G/B WAV + meta.json -> obrázek', variable=self.mode, value='decode', command=self._update_mode).pack(anchor='w')

        self.encode_frame = ttk.LabelFrame(root, text='Encode', padding=10)
        self.encode_frame.pack(fill='x', pady=(10, 0))
        self._build_encode(self.encode_frame)

        self.decode_frame = ttk.LabelFrame(root, text='Decode', padding=10)
        self.decode_frame.pack(fill='x', pady=(10, 0))
        self._build_decode(self.decode_frame)

        actions = ttk.Frame(root)
        actions.pack(fill='x', pady=(12, 0))
        ttk.Button(actions, text='Spustit', command=self.run_action).pack(side='left')
        ttk.Button(actions, text='Vyčistit log', command=self.clear_log).pack(side='left', padx=(8, 0))

        log_frame = ttk.LabelFrame(root, text='Log', padding=8)
        log_frame.pack(fill='both', expand=True, pady=(12, 0))
        self.log = ScrolledText(log_frame, height=18, wrap='word')
        self.log.pack(fill='both', expand=True)

    def _build_encode(self, parent):
        self._path_row(parent, 'Vstupní obrázek:', self.input_image, self.pick_input_image, 0)
        self._path_row(parent, 'Output prefix:', self.output_prefix, self.pick_output_prefix, 1, button_text='Uložit jako')

        ttk.Label(parent, text='Sample rate:').grid(row=2, column=0, sticky='w', padx=(0, 8), pady=6)
        ttk.Entry(parent, textvariable=self.sample_rate, width=12).grid(row=2, column=1, sticky='w', pady=6)

        for i in range(3):
            parent.columnconfigure(i, weight=1 if i == 1 else 0)

    def _build_decode(self, parent):
        self._path_row(parent, 'R WAV:', self.r_wav, lambda: self.pick_file(self.r_wav, [('WAV files', '*.wav')]), 0)
        self._path_row(parent, 'G WAV:', self.g_wav, lambda: self.pick_file(self.g_wav, [('WAV files', '*.wav')]), 1)
        self._path_row(parent, 'B WAV:', self.b_wav, lambda: self.pick_file(self.b_wav, [('WAV files', '*.wav')]), 2)
        self._path_row(parent, 'Meta JSON:', self.meta_json, lambda: self.pick_file(self.meta_json, [('JSON files', '*.json')]), 3)
        self._path_row(parent, 'Výstupní obrázek:', self.output_image, self.pick_output_image, 4, button_text='Uložit jako')

        ttk.Label(parent, text='Fit mode:').grid(row=5, column=0, sticky='w', padx=(0, 8), pady=6)
        combo = ttk.Combobox(parent, textvariable=self.fit_mode, values=['strict', 'truncate', 'pad'], state='readonly', width=12)
        combo.grid(row=5, column=1, sticky='w', pady=6)

        for i in range(3):
            parent.columnconfigure(i, weight=1 if i == 1 else 0)

    def _path_row(self, parent, label, var, cmd, row, button_text='Procházet'):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 8), pady=6)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky='ew', pady=6)
        ttk.Button(parent, text=button_text, command=cmd).grid(row=row, column=2, sticky='ew', pady=6)

    def _update_mode(self):
        if self.mode.get() == 'encode':
            self.encode_frame.state(['!disabled'])
            self.decode_frame.state(['disabled'])
            self._set_children_state(self.encode_frame, 'normal')
            self._set_children_state(self.decode_frame, 'disabled')
        else:
            self.decode_frame.state(['!disabled'])
            self.encode_frame.state(['disabled'])
            self._set_children_state(self.decode_frame, 'normal')
            self._set_children_state(self.encode_frame, 'disabled')

    def _set_children_state(self, widget, state):
        for child in widget.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass

    def pick_file(self, var, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            var.set(path)

    def pick_input_image(self):
        path = filedialog.askopenfilename(filetypes=[('Images', '*.png *.bmp *.tif *.tiff *.jpg *.jpeg'), ('All files', '*.*')])
        if path:
            self.input_image.set(path)
            p = Path(path)
            if not self.output_prefix.get():
                self.output_prefix.set(str(p.with_suffix('')))

    def pick_output_prefix(self):
        path = filedialog.asksaveasfilename(defaultextension='', filetypes=[('All files', '*.*')])
        if path:
            self.output_prefix.set(path)

    def pick_output_image(self):
        path = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[('PNG', '*.png'), ('BMP', '*.bmp'), ('TIFF', '*.tif *.tiff')])
        if path:
            self.output_image.set(path)

    def log_write(self, text):
        self.log.insert('end', text + '\n')
        self.log.see('end')
        self.update_idletasks()

    def clear_log(self):
        self.log.delete('1.0', 'end')

    def run_action(self):
        try:
            if self.mode.get() == 'encode':
                self.run_encode()
            else:
                self.run_decode()
        except Exception as e:
            self.log_write(f'CHYBA: {e}')
            messagebox.showerror('Chyba', str(e))

    def run_encode(self):
        input_image = self.input_image.get().strip()
        output_prefix = self.output_prefix.get().strip()
        if not input_image:
            raise ValueError('Vyber vstupní obrázek.')
        if not output_prefix:
            raise ValueError('Zadej output prefix.')

        sample_rate = int(self.sample_rate.get())
        self.log_write('Spouštím encode...')
        result = encode_image(input_image, output_prefix, sample_rate)
        self.log_write(f'Rozměry: {result["width"]} x {result["height"]}')
        self.log_write(f'R: {result["r_path"]}')
        self.log_write(f'G: {result["g_path"]}')
        self.log_write(f'B: {result["b_path"]}')
        self.log_write(f'META: {result["meta_path"]}')
        messagebox.showinfo('Hotovo', 'Encode proběhl úspěšně.')

    def run_decode(self):
        r = self.r_wav.get().strip()
        g = self.g_wav.get().strip()
        b = self.b_wav.get().strip()
        meta = self.meta_json.get().strip()
        out = self.output_image.get().strip()
        fit = self.fit_mode.get().strip()

        if not all([r, g, b, meta, out]):
            raise ValueError('Vyplň všechny vstupy pro decode.')

        self.log_write('Spouštím decode...')
        result = decode_image(r, g, b, meta, out, fit)
        self.log_write(f'Rozměry: {result["width"]} x {result["height"]}')
        self.log_write(f'Očekávaná délka kanálu: {result["expected"]} B')
        self.log_write(f'R params: {result["r_params"]}')
        self.log_write(f'G params: {result["g_params"]}')
        self.log_write(f'B params: {result["b_params"]}')
        self.log_write(f'Výstup: {result["output_image"]}')
        messagebox.showinfo('Hotovo', 'Decode proběhl úspěšně.')


if __name__ == '__main__':
    app = App()
    app.mainloop()