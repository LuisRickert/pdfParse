import logging
import re
import shutil
from datetime import datetime as dt
from pathlib import Path

import hydra
import pypdf
from omegaconf import DictConfig
from tqdm import tqdm

logger = logging.getLogger(__name__)


def get_files(file_list: list, src: Path) -> None:
    if src.is_dir():
        for file in src.iterdir():
            if file.is_file() and file.name.endswith(".pdf"):
                file_list.append(file)
            elif file.is_dir():
                get_files(file_list, file)
            elif file.is_file():
                pass
            else:
                logger.error("Something went wrong getting all the files")
                raise ValueError("Something went wrong getting all files")

    elif src.is_file() and src.name.endswith(".pdf"):
        file_list.append(src)


@hydra.main(version_base=None, config_path="../conf", config_name="config")
def start(cfg: DictConfig):
    if cfg.parser.log_level == "info":
        logger.setLevel(logging.INFO)
    elif cfg.parser.log_level == "debug":
        logger.setLevel(logging.DEBUG)
    elif cfg.parser.log_level == "error":
        logger.setLevel(logging.ERROR)
    else:
        raise ValueError("unrecognized log level %s" % cfg.parser.log_level)

    read_format = cfg.parser.datereadformat
    write_format = cfg.parser.datewriteformat

    target_path = Path(cfg.parser.targetpath)
    target_path.mkdir(parents=True, exist_ok=True)

    extracted_data = []
    to_extract = []

    for src in cfg.parser.src:
        src = Path(src)
        if src.is_dir():
            src.mkdir(parents=True, exist_ok=True)
        get_files(to_extract, src)

    extracted_data = [
        extract_data(file, read_format)
        for file in tqdm(
            to_extract,
            desc=f"working on {len(to_extract)} files ...",
            total=len(to_extract),
        )
    ]

    for file in extracted_data:
        if (
            file.get("vorgang") is None
            or file.get("date") is None
            or file.get("ISIN") is None
            or file.get("broker") is None
            or file.get("vnum") is None
        ):
            logger.warning(
                "error on vorgang=%s,date=%s,ISIN=%s,broker=%s, file=%s"
                % (
                    file.get("vorgang"),
                    file.get("date"),
                    file.get("ISIN"),
                    file.get("broker"),
                    file.get("name"),
                )
            )

        else:
            write_file(file, target_path, write_format, overwrite=cfg.parser.overwrite)


def extract_data(file: Path, readformat: str) -> dict:
    date_found = False

    file_data = {}
    file_data["name"] = str(file)
    file_data["content"] = pypdf.PdfReader(file).pages[0].extract_text()
    content: list[str] = file_data["content"].split("\n")

    for line in content:
        try:
            if "Wertpapierabrechnung: " in line:
                if file_data.get("vorgang") is None:
                    file_data["vorgang"] = line.split(": ")[1]
                else:
                    raise ValueError(
                        "found multiple 'vorgang' candidates in %s" % file_data["name"]
                    )
            elif "Vorgangs-Nr" in line:
                if file_data.get("vnum") is None:
                    file_data["vnum"] = line.split(".:")[1].strip()
            elif "Ausschüttung" in line:
                if file_data.get("vorgang") is None:
                    file_data["vorgang"] = line.strip()
                else:
                    if not file_data["vorgang"] == line:
                        raise ValueError(
                            "found multiple 'vorgang' candidates in %s found %s %s "
                            % file_data["name"],
                            line,
                            file_data["vorgang"],
                        )
            elif "Depoteinlieferung" in line:
                if file_data.get("vorgang") is None:
                    file_data["vorgang"] = line.strip()
                else:
                    if not file_data["vorgang"] == line:
                        raise ValueError(
                            "found multiple 'vorgang' candidates in %s found %s %s "
                            % file_data["name"],
                            line,
                            file_data["vorgang"],
                        )
            elif (
                not date_found
                and re.match("[0-9]{2}\.[0-9]{2}\.[0-9]{4}", line) is not None
            ):
                file_data["date"] = dt.strptime(line, readformat)
                date_found = True

            elif "ISIN: " in line:
                file_data["ISIN"] = line.split(": ")[1].strip()
            elif "Scalable Capital GmbH" in line or "Scalable Capital":
                file_data["broker"] = "ScalableCapital"
            else:
                pass
        except ValueError as e:
            logger.warning(e)
    return file_data


def create_name(file_data: dict, write_format: str, num: int = 0) -> str:
    new_name = (
        dt.strftime(file_data["date"], write_format)
        + "_"
        + file_data["broker"]
        + "_"
        + file_data["ISIN"]
        + "_"
        + file_data["vnum"]
        + "_"
        + file_data["vorgang"]
    )

    if num > 0:
        new_name = new_name + ("_%s" % str(num))

    return new_name + ".pdf"


def write_file(
    file_data: dict, targetPath: Path, write_format, overwrite: bool = True
) -> None:
    file_count = 0
    # generate filename an path
    filePath = Path(
        targetPath
        / create_name(file_data=file_data, write_format=write_format, num=file_count)
    )

    # if target path exists rename increment file counter +1
    if filePath.exists() and not overwrite:
        # set while condition
        file_count_flag = True
        while file_count_flag:
            # break condition max tries
            if file_count > 50:
                raise ValueError(
                    "Something went wrong with file creation. reached max attemps limit file: %s generated name : %s"
                    % (file_data["name"], filePath)
                )
            file_count += 1
            # create new file
            filePath = Path(
                targetPath / create_name(file_data, write_format, file_count)
            )

            # reevalutate while condition
            file_count_flag = filePath.exists()

    shutil.copy2(file_data["name"], filePath)


if __name__ == "__main__":
    start()
