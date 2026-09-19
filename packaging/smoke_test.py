"""Prueba automática de la app ya empaquetada: arranca, descarga de verdad, comprueba y cierra.

Uso:
  python packaging/smoke_test.py --app "dist/NactionX Downloader.app/Contents/MacOS/NactionX Downloader"
  python packaging/smoke_test.py --app "build/portable/NactionX Downloader/runtime/pythonw.exe"
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

YOUTUBE = 'https://www.youtube.com/watch?v=jNQXAC9IVRw'
failures = []


def make_sample(ffmpeg, path):
    """Crea un vídeo de prueba con audio usando el FFmpeg incluido: sin depender de ninguna web."""
    subprocess.run([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
                    '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=15:duration=6',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-shortest', str(path)], check=True)
    return path


def serve(folder):
    """Servidor HTTP local para que la app descargue el vídeo de prueba."""
    import functools
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import threading

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(folder)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f'http://127.0.0.1:{httpd.server_address[1]}/muestra.mp4'


def check(condition, description, detail=''):
    print(f'{"OK  " if condition else "FALLO"}  {description}{"" if condition else f"  -> {detail}"}', flush=True)
    if not condition:
        failures.append(description)
    return condition


def api(info, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f'http://127.0.0.1:{info["port"]}{path}', data=data, method='POST' if body is not None else 'GET',
        headers={'X-NactionX-Token': info['token'], 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def command(app, data_dir):
    if app.name.lower() == 'pythonw.exe':
        return [str(app), '-m', 'nactionx', '--data-dir', str(data_dir)]
    return [str(app), '--data-dir', str(data_dir)]


def launch(app, data_dir):
    proc = subprocess.Popen(command(app, data_dir), cwd=str(app.parent.parent if app.name.lower() == 'pythonw.exe' else app.parent))
    instance = Path(data_dir) / 'instance.json'
    for _ in range(180):
        time.sleep(0.5)
        if proc.poll() is not None:
            raise SystemExit(f'La app se cerró sola con código {proc.returncode}')
        if instance.exists():
            try:
                info = json.loads(instance.read_text(encoding='utf-8'))
                if info.get('pid') == proc.pid:
                    api(info, '/api/state')
                    return proc, info
            except Exception:
                pass
    raise SystemExit('La app no arrancó a tiempo')


def find_bin(app, tool):
    name = f'{tool}.exe' if sys.platform == 'win32' else tool
    for candidate in (app.parent.parent / 'app' / 'bin' / name,        # Windows portable
                      app.parent.parent / 'Frameworks' / 'bin' / name,  # macOS .app
                      app.parent / '_internal' / 'bin' / name):         # PyInstaller onedir
        if candidate.is_file():
            return str(candidate)
    return shutil.which(tool)


def duration(ffprobe, path):
    if not ffprobe:
        return None
    out = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', required=True)
    parser.add_argument('--work', default=os.path.join(os.path.expanduser('~'), 'nactionx-smoke'))
    args = parser.parse_args()
    app = Path(args.app).resolve()
    work = Path(args.work).resolve()
    data_dir, downloads, sample_dir = work / 'data', work / 'descargas', work / 'origen'
    shutil.rmtree(work, ignore_errors=True)
    data_dir.mkdir(parents=True)
    sample_dir.mkdir(parents=True)

    ffmpeg, ffprobe = find_bin(app, 'ffmpeg'), find_bin(app, 'ffprobe')
    check(bool(ffmpeg and ffprobe), 'FFmpeg y FFprobe están junto a la app', f'{ffmpeg} / {ffprobe}')
    make_sample(ffmpeg, sample_dir / 'muestra.mp4')
    httpd, video_url = serve(sample_dir)

    started = time.time()
    proc, info = launch(app, data_dir)
    print(f'Arranque en {time.time() - started:.1f} s (pid {proc.pid}, puerto {info["port"]})', flush=True)

    boot = api(info, '/api/bootstrap')
    components = boot['components']
    print('Componentes:', json.dumps(components, ensure_ascii=False)[:400], flush=True)
    check(boot['app']['desktop'], 'La app arranca en modo escritorio')
    check(components['ffmpeg_source'] == 'incluido', 'FFmpeg incluido en el paquete', components.get('ffmpeg_source'))
    check(components['js_source'] == 'incluido', 'Motor JavaScript incluido', components.get('js_source'))
    check(bool(components['ejs']), 'Componente yt-dlp-ejs presente')
    check(not components['issues'], 'Sin problemas de componentes', str(components['issues']))
    # En macOS, la app empaquetada busca los certificados en la ruta que OpenSSL trae compilada. Esa
    # ruta existe en la máquina que compila, así que aquí nunca se vería el fallo: lo que hay que
    # comprobar es que el paquete de certificados viaja DENTRO de la app, que es lo que lo arregla
    # en cualquier ordenador.
    check(components.get('certificates') == 'certifi', 'Los certificados HTTPS viajan dentro de la app',
          str(components.get('certificates')))
    update = api(info, '/api/app/update-check', {}, timeout=60)
    check('certificate' not in (update.get('message', '') + update.get('error', '')).lower()
          and 'SSL' not in update.get('error', ''), 'La comprobación de versión no falla por certificados',
          f'{update.get("state")}: {update.get("message")}')
    print(f'Comprobación de versión: {update.get("state")} — {update.get("message")}', flush=True)

    api(info, '/api/settings', {'values': {'folder': str(downloads)}})
    api(info, '/api/add', {'items': [{'url': video_url, 'title': 'prueba'}], 'options': {'mode': 'video'}})
    api(info, '/api/add', {'items': [{'url': video_url, 'title': 'prueba'}],
                           'options': {'mode': 'audio', 'audio_format': 'mp3', 'start': '0:02', 'end': '0:05'}})

    second = subprocess.run(command(app, data_dir), timeout=120)
    check(second.returncode == 0 and proc.poll() is None, 'Instancia única: la segunda se cierra sola')

    deadline = time.time() + 300
    jobs = []
    while time.time() < deadline:
        jobs = api(info, '/api/state')['jobs']
        if jobs and all(j['status'] in ('done', 'error') for j in jobs):
            break
        time.sleep(2)
    for job in jobs:
        print(f'  {job["status"]:6} {job["format_label"]:22} {Path(job["filepath"]).name if job["filepath"] else ""} {job["error"]}', flush=True)
    check(all(j['status'] == 'done' for j in jobs) and len(jobs) == 2, 'Las dos descargas terminan bien',
          '; '.join(f'{j["status"]}: {j["error"]}' for j in jobs))

    httpd.shutdown()
    files = sorted(p for p in downloads.iterdir() if p.is_file()) if downloads.is_dir() else []
    print('Archivos:', [f'{p.name} ({p.stat().st_size} bytes)' for p in files], flush=True)
    check(len(files) == 2 and all(p.stat().st_size > 10000 for p in files), 'Se crean los dos archivos con contenido')
    clip = next((p for p in files if p.suffix == '.mp3'), None)
    check(clip is not None and 'recorte 00m02s-00m05s' in clip.name, 'El recorte conserva el nombre completo y su sufijo',
          clip.name if clip else 'sin mp3')
    if clip:
        seconds = duration(ffprobe, clip)
        check(seconds is not None and abs(seconds - 3) < 0.6, 'El recorte dura 3 segundos', f'{seconds} s')

    try:
        result = api(info, '/api/info', {'query': YOUTUBE}, timeout=180)
        print(f'YouTube: «{result["title"]}» con {len(result["qualities"])} calidades', flush=True)
    except Exception as e:  # los servidores de CI suelen estar bloqueados por YouTube: informativo
        print(f'YouTube no disponible desde esta máquina (informativo): {e}', flush=True)

    api(info, '/api/app/quit', {})
    try:
        proc.wait(timeout=60)
        closed = True
    except subprocess.TimeoutExpired:
        closed = False
        proc.kill()
    check(closed, 'La app se cierra de forma ordenada')
    check(not (data_dir / 'instance.json').exists(), 'Se limpia el archivo de instancia')
    check((data_dir / 'queue.json').exists(), 'La cola queda guardada en disco')

    if failures:
        log = data_dir / 'logs' / 'nactionx.log'
        if log.exists():
            print('\n--- registro de la app ---\n' + '\n'.join(log.read_text(encoding='utf-8', errors='replace').splitlines()[-40:]))
        print(f'\n{len(failures)} comprobaciones fallaron: {failures}')
        return 1
    print('\nTodas las comprobaciones pasaron.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
