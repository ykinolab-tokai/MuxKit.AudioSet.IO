import csv
import logging
import os
import shutil
import subprocess
import sys
import asyncio
from aiofiles import open as aio_open
from typing import Union
import multiprocessing

try:
    from downloader_configs import *
except ImportError:
    sys.stderr.write("!Panic!: Config file not found.")
    exit(-1)

VERSION = [1, 0, 2]

async def run_subprocess(cmd):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logging.error(f'Command failed with exit code {proc.returncode}\n{stderr.decode()}')
    return proc.returncode == 0

async def download_video_clip(url: str, youtube_id: str, start_sec: int, end_sec: int, save_dir: str) -> Union[str, None]:
    output_name = os.path.join(save_dir, f"{youtube_id}.mp4")
    try:
        download_cmd = [
            "yt-dlp",
            "-f", "bestaudio",
            "--external-downloader", "ffmpeg",
            "--external-downloader-args", f"ffmpeg_i:-ss {start_sec} -to {end_sec}",
            "-o", output_name,
            url
        ]
        success = await run_subprocess(download_cmd)
        if not success:
            return None
        return output_name
    except Exception as e:
        logging.error(f"Download failed for {url}: {e}")
        return None

async def extract_audio(video_file: str, save_dir: str) -> Union[str, None]:
    basename = os.path.basename(video_file)
    name, _ = os.path.splitext(basename)
    output_name = os.path.join(save_dir, f"{name}.wav")
    success = await run_subprocess([
        "ffmpeg",
        "-i", video_file,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        output_name
    ])
    if not success:
        return None
    return output_name

async def process_csv_file(csv_file: str, timer: int, remove_exist: bool, youtube_url_fmt: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s - pid:%(process)d", handlers=[
                        logging.FileHandler(filename=f"{csv_file}_dl.log", mode="w"), logging.StreamHandler(stream=sys.stdout)])
    save_dir = f"./{csv_file}.splits/"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    else:
        if remove_exist:
            shutil.rmtree(save_dir)
            os.makedirs(save_dir)

    tasks = []
    async with aio_open(f"{csv_file}.split-pos.csv", "w") as split_audio_positive_label:
        async with aio_open(csv_file, "r") as csv_fin:
            reader = csv.reader(await csv_fin.readlines())
            for i, line in enumerate(reader):
                if 0 < timer == i:
                    break
                raw = {"YTID": line[0], "start_sec": int(float(line[1].replace(" ", ""))), "end_sec": int(float(line[2].replace(" ", ""))), "positive_labels": line[3:]}
                url = youtube_url_fmt.format(YTID=raw["YTID"])
                task = asyncio.create_task(download_and_process(url, raw["YTID"], raw["start_sec"], raw["end_sec"], save_dir, split_audio_positive_label, raw["positive_labels"]))
                tasks.append(task)

            await asyncio.gather(*tasks)

async def download_and_process(url, ytid, start_sec, end_sec, save_dir, split_audio_positive_label, positive_labels):
    video_file = await download_video_clip(url, ytid, start_sec, end_sec, save_dir)
    if video_file:
        audio_file = await extract_audio(video_file, save_dir)
        if audio_file:
            await split_audio_positive_label.write(f'{audio_file}, {"{}".format(",".join(positive_labels))}\n')
            await split_audio_positive_label.flush()
        os.remove(video_file)

def run_process_csv_file(csv_file, timer, remove_exist, youtube_url_fmt):
    asyncio.run(process_csv_file(csv_file, timer, remove_exist, youtube_url_fmt))

def main():
    if DEBUG:
        run_process_csv_file(CSV_FILE_NAMES[0], TIMER, REMOVE_EXIST_DOWNLOADS, YTB_URL_FORMAT)
    else:
        with multiprocessing.Pool() as pool:
            pool.starmap(run_process_csv_file, [(csv_file, TIMER, REMOVE_EXIST_DOWNLOADS, YTB_URL_FORMAT) for csv_file in CSV_FILE_NAMES])

if __name__ == "__main__":
    main()
