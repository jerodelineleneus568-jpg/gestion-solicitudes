import argparse
import re
from pathlib import Path

from app import create_app
from app.models.solicitud_model import SolicitudModel


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--ruta",
        help="Ruta al Excel original descargado de WebLun",
    )

    args = parser.parse_args()
    app = create_app()

    with app.app_context():
        if args.ruta:
            ruta = Path(args.ruta).resolve()

        else:
            carpeta = Path(app.config["UPLOAD_FOLDER"])

            archivos = [
                archivo
                for archivo in carpeta.rglob("original.*")
                if archivo.suffix.lower() in {".xlsx", ".xls"}
                and re.fullmatch(
                    r"[0-9a-f]{32}",
                    archivo.parent.name,
                )
                and (
                    archivo.parent
                    / "Reporte_Rayen_Activos.xlsx"
                ).is_file()
            ]

            if not archivos:
                raise SystemExit(
                    "No hay un Excel original disponible. "
                    "Realiza una extracción desde el panel."
                )

            ruta = max(
                archivos,
                key=lambda archivo: archivo.stat().st_mtime,
            ).resolve()

        print("Excel que se sincronizará:", ruta)

        cantidad = SolicitudModel.sincronizar_desde_excel(
            ruta
        )

        print(
            "Sincronización completada:",
            cantidad,
            "solicitudes actualizadas.",
        )


if __name__ == "__main__":
    main()