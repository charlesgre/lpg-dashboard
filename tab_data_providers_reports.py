# tab_data_providers_reports.py

import streamlit as st
from pathlib import Path
import base64

# Dossiers de reports, relatifs à ce fichier
BASE_DIR = Path(__file__).resolve().parent
REPORTS_ROOT = BASE_DIR / "Data providers reports"

PROVIDER_FOLDERS = {
    "EA reports": REPORTS_ROOT / "EA reports",
    "Platts reports": REPORTS_ROOT / "Platts reports",
}


def _render_pdf_list(folder: Path):
    """
    Affiche la liste des PDF d'un dossier :
      - titre propre
      - bouton download
      - visionneuse intégrée (iframe)
    """
    if not folder.exists():
        st.info(f"Dossier introuvable : `{folder}`")
        return

    pdf_files = sorted(
        folder.glob("*.pdf"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not pdf_files:
        st.info("Aucun rapport PDF trouvé dans ce dossier.")
        return

    for pdf_path in pdf_files:
        # Titre lisible à partir du nom de fichier
        title = pdf_path.stem.replace("_", " ").replace("-", " ").title()

        with st.expander(title, expanded=False):
            with open(pdf_path, "rb") as f:
                data = f.read()

            # bouton de téléchargement
            st.download_button(
                label="📥 Download",
                data=data,
                file_name=pdf_path.name,
                mime="application/pdf",
                key=f"download_{pdf_path.name}",
            )

            # visionneuse intégrée
            b64 = base64.b64encode(data).decode("utf-8")
            iframe_html = f"""
            <iframe
                src="data:application/pdf;base64,{b64}"
                width="100%"
                height="600"
                style="border:none;"
            ></iframe>
            """
            st.markdown(iframe_html, unsafe_allow_html=True)


def render():
    """
    Point d'entrée de l’onglet 'Latest reports'
    (même style que tes autres fichiers tab_*.py : une fonction render()).
    """
    st.header("Latest reports")

    # Choix du provider (EA / Platts)
    provider = st.radio(
        "Choose data provider:",
        options=list(PROVIDER_FOLDERS.keys()),
        horizontal=True,
    )

    folder = PROVIDER_FOLDERS[provider]

    st.markdown(
        f"### {provider}\n"
        f"_Source folder_: `{folder.relative_to(BASE_DIR) if folder.exists() else folder}`"
    )

    _render_pdf_list(folder)
