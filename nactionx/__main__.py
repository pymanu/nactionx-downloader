"""Punto de entrada: `python -m nactionx` (ventana) o `python -m nactionx --browser` (desarrollo)."""
import argparse
import os
import sys


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog='nactionx')
    parser.add_argument('--browser', action='store_true', help='Servir la interfaz en el navegador (desarrollo)')
    parser.add_argument('--no-open', action='store_true', help='Con --browser, no abrir el navegador')
    parser.add_argument('--debug', action='store_true', help='Registro detallado y herramientas de desarrollo')
    parser.add_argument('--data-dir', help='Carpeta de datos alternativa (pruebas)')
    parser.add_argument('--port', type=int, default=0,
                        help='Puerto fijo en 127.0.0.1 (para poner un proxy delante). Por defecto, uno libre')
    parser.add_argument('--wait-pid', type=int, help=argparse.SUPPRESS)
    args, _unknown = parser.parse_known_args(argv)  # macOS puede añadir argumentos propios (-psn_...)
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.data_dir:
        os.environ['NACTIONX_DATA_DIR'] = args.data_dir

    from nactionx import components, log, platform_utils
    log.setup(debug=args.debug)
    logger = log.get('main')
    if args.wait_pid:
        platform_utils.wait_for_exit(args.wait_pid)

    # La versión actualizada de yt-dlp debe activarse antes de importar yt_dlp en ningún sitio
    overlay = components.apply_overlay()
    try:
        version = components.verify_ytdlp()
        logger.info('Motor yt-dlp %s%s', version, ' (actualizado)' if overlay else '')
    except Exception as e:
        if overlay:
            components.disable_overlay(e)
            platform_utils.spawn_relaunch()
            return 1
        logger.exception('El motor yt-dlp no se pudo cargar')
        raise

    from nactionx import api, desktop, manager, settings
    return desktop.run(args, settings.Settings(), components.Components(), manager.Manager, api.ApiServer,
                       manager.migrate_legacy)


def run():
    """Como main(), pero si algo impide arrancar muestra un aviso en lugar de cerrarse sin decir nada."""
    try:
        return main()
    except SystemExit:
        raise
    except BaseException as e:
        try:
            from nactionx import APP_NAME, log, paths, platform_utils
            log.get('main').exception('Error fatal al arrancar')
            platform_utils.message_box(APP_NAME, f'No se pudo iniciar {APP_NAME}:\n\n{e}\n\n'
                                                 f'Encontrarás más detalles en el registro:\n{paths.sub_dir("logs")}')
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    sys.exit(run())
