#!/usr/bin/env python3
import argparse
import json
import wave
import struct
from pathlib import Path
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


def read_mono_wav(wav_path: str) -> tuple[bytes, tuple]:
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

    print(f'Hotovo: {input_image}')
    print(f'  {r_path}')
    print(f'  {g_path}')
    print(f'  {b_path}')
    print(f'  {meta_path}')


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

    print(f'Hotovo: {output_image}')
    print('Parametry WAV:')
    print(f'  R: {r_params}')
    print(f'  G: {g_params}')
    print(f'  B: {b_params}')
    print(f'Použitý režim fit: {fit_mode}')
    print(f'Očekávaná délka kanálu: {expected} B')


def main():
    parser = argparse.ArgumentParser(
        description='Převod obrázku na 3 samostatné WAV stopy (R, G, B) + meta.json a zpět.'
    )
    sub = parser.add_subparsers(dest='mode', required=True)

    enc = sub.add_parser('encode', help='Převede obrázek na tři WAV stopy + meta.json')
    enc.add_argument('input_image', help='Vstupní obrázek')
    enc.add_argument('output_prefix', help='Prefix výstupních souborů')
    enc.add_argument('--sample-rate', type=int, default=48000, help='Vzorkovací frekvence WAV')

    dec = sub.add_parser('decode', help='Složí tři WAV stopy zpět do obrázku')
    dec.add_argument('input_r_wav', help='WAV pro červený kanál')
    dec.add_argument('input_g_wav', help='WAV pro zelený kanál')
    dec.add_argument('input_b_wav', help='WAV pro modrý kanál')
    dec.add_argument('meta_json', help='Meta JSON soubor z encode')
    dec.add_argument('output_image', help='Výstupní obrázek')
    dec.add_argument(
        '--fit',
        choices=['strict', 'truncate', 'pad'],
        default='truncate',
        help='Jak řešit nesoulad délky stopy vůči width*height'
    )

    args = parser.parse_args()

    if args.mode == 'encode':
        encode_image(args.input_image, args.output_prefix, args.sample_rate)

    elif args.mode == 'decode':
        suffix = Path(args.output_image).suffix.lower()
        if suffix not in {'.png', '.bmp', '.tiff', '.tif'}:
            raise ValueError('Doporučený výstup je bezeztrátový formát, např. PNG.')

        decode_image(
            args.input_r_wav,
            args.input_g_wav,
            args.input_b_wav,
            args.meta_json,
            args.output_image,
            args.fit
        )


if __name__ == '__main__':
    main()