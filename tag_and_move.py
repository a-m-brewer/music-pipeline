#!/usr/bin/env python3

import argparse
from enum import IntEnum, StrEnum
import os
import pathlib
from typing import Optional
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich import print
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from mutagen import File
from mutagen.mp3 import HeaderNotFoundError
from mutagen.id3 import Frame, ID3Tags, TIT2, TPE1, TALB, TDRC, TRCK, TCON, COMM, TPE2, TCOM, TPOS
from mutagen.wave import WAVE
import glob
import pygame


parser = argparse.ArgumentParser(description='Tag music files and move them to a new directory')

parser.add_argument('source', type=str, help='Source directory')
parser.add_argument('destination', type=str, nargs='?', help='Destination directory (optional)')
parser.add_argument('discard', type=str, nargs='?', help='Discard directory (optional)')

class ExitCodes(IntEnum):
    SOURCE_DIR_NOT_FOUND = 1
    DESTINATION_DIR_NOT_FOUND = 2

class SelectionOptions(StrEnum):
    TITLE = '[bold magenta](T)[/bold magenta]itle'
    ARTIST = '[bold cyan](A)[/bold cyan]rtist'
    ALBUM = 'A[bold blue](l)[/bold blue]bum'
    YEAR = '[bold turquoise4](Y)[/bold turquoise4]ear'
    TRACK_NUMBER = 'T[bold magenta](r)[/bold magenta]ack Number'
    GENRE = '[bold purple4](G)[/bold purple4]enre'
    COMMENT = '[bold orange4](C)[/bold orange4]omment'
    ALBUM_ARTIST = 'Al[bold dark_violet](b)[/bold dark_violet]bum Artist'
    COMPOSER = 'Co[bold plum4](m)[/bold plum4]poser'
    DISC_NUMBER = 'D[bold hot_pink](i)[/bold hot_pink]sc Number'
    PLAY = '[bold blue](P)[/bold blue]lay'
    STOP = 'st[bold red](o)[/bold red]p'
    SAVE = '[bold yellow](S)[/bold yellow]kip'
    NEXT = '[bold green](N)[/bold green]ext'
    DELETE = '[bold red](D)[/bold red]elete'
    DISCARD = '[bold red](dd)[/bold red]iscard'
    QUIT = '[bold red](Q)[/bold red]uit'

selection_prompt = ', '.join([option.value for option in SelectionOptions])

class Id3Tags(StrEnum):
    TITLE = 'TIT2'
    ARTIST = 'TPE1'
    ALBUM = 'TALB'
    RECORDING_TIME = 'TDRC'
    YEAR = 'TYER'
    TRACK_NUMBER = 'TRCK'
    GENRE = 'TCON'
    COMMENT = 'COMM'
    ALBUM_ARTIST = 'TPE2'
    COMPOSER = 'TCOM'
    DISC_NUMBER = 'TPOS'
    

class Tags:  
    def __init__(self,
                 file,
                 file_path: str):
        self.file = file
        self.file_path = file_path

    @property
    def title(self) -> Optional[str]:
        return self._get_tags(Id3Tags.TITLE)

    @title.setter
    def title(self, value: str):
        if value is None or value.strip() == '':
            return

        tit2 = TIT2()
        tit2.text = value
        self._set_tags(Id3Tags.TITLE, tit2)
    
    @property
    def artist(self) -> Optional[str]:
        return self._get_tags(Id3Tags.ARTIST)
    
    @artist.setter
    def artist(self, value: str):
        if value is None or value.strip() == '':
            return

        tpe1 = TPE1()
        tpe1.text = value
        self._set_tags(Id3Tags.ARTIST, tpe1)
        
    @property
    def album(self) -> Optional[str]:
        return self._get_tags(Id3Tags.ALBUM)
    
    @album.setter
    def album(self, value: str):
        if value is None or value.strip() == '':
            return

        talb = TALB()
        talb.text = value
        self._set_tags(Id3Tags.ALBUM, talb)
        
    @property
    def year(self) -> Optional[str]:
        year_timestamp = self._get_tags(Id3Tags.RECORDING_TIME)
        
        if year_timestamp:
            return year_timestamp.text
        else:
            return None
    
    @year.setter
    def year(self, value: str):
        if value is None or value.strip() == '':
            return
        tdrc = TDRC()
        tdrc.text = value
        self._set_tags(Id3Tags.RECORDING_TIME, tdrc)

    @property
    def track_number(self) -> Optional[str]:
        return self._get_tags(Id3Tags.TRACK_NUMBER)
    
    @track_number.setter
    def track_number(self, value: str):
        if value is None or value.strip() == '':
            return
        trck = TRCK()
        trck.text = value
        self._set_tags(Id3Tags.TRACK_NUMBER, trck)
    
    @property
    def genre(self) -> Optional[str]:
        return self._get_tags(Id3Tags.GENRE)
    
    @genre.setter
    def genre(self, value: str):
        if value is None or value.strip() == '':
            return
        tcon = TCON()
        tcon.genres = value
        self._set_tags(Id3Tags.GENRE, tcon)
    
    @property
    def comment(self) -> Optional[str]:
        return self._get_tags(Id3Tags.COMMENT)
    
    @comment.setter
    def comment(self, value: str):
        if value is None or value.strip() == '':
            return
        comm = COMM()
        comm.text = value
        self._set_tags(Id3Tags.COMMENT, comm)
    
    @property
    def album_artist(self) -> Optional[str]:
        return self._get_tags(Id3Tags.ALBUM_ARTIST)
    
    @album_artist.setter
    def album_artist(self, value: str):
        if value is None or value.strip() == '':
            return
        tpe2 = TPE2()
        tpe2.text = value
        self._set_tags(Id3Tags.ALBUM_ARTIST, tpe2)
    
    @property
    def composer(self) -> Optional[str]:
        return self._get_tags(Id3Tags.COMPOSER)
    
    @composer.setter
    def composer(self, value: str):
        if value is None or value.strip() == '':
            return
        tcom = TCOM()
        tcom.text = value
        self._set_tags(Id3Tags.COMPOSER, tcom)
    
    @property
    def disc_number(self) -> Optional[str]:
        return self._get_tags(Id3Tags.DISC_NUMBER)
    
    @disc_number.setter
    def disc_number(self, value: str):
        if value is None or value.strip() == '':
            return
        tpos = TPOS()
        tpos.text = value
        self._set_tags(Id3Tags.DISC_NUMBER, tpos)
        
    def save(self):
        self.file.save()
        self.file = File(self.file_path)
    
    def _get_tags(self, tag: Id3Tags):
        if isinstance(self.file.tags, ID3Tags):
            t = self.file.tags.getall(tag.value)
            if len(t) > 0:
                if len(t[0].text) > 0:
                    return t[0].text[0]
            return None
        
        raise NotImplementedError("Only ID3 tags are supported")
    
    def _set_tags(self, tag: Id3Tags, value: Frame):
        if isinstance(self.file.tags, ID3Tags):
            self.file.tags.setall(tag.value, [
                value
            ])
        else:
            raise NotImplementedError("Only ID3 tags are supported")

def error(message):
    print(f"[red]{message}[/red]")

def source_audio_files_generator(source):
    for file in glob.iglob(f"{source}/**/*", recursive=True):
        if os.path.isfile(file):
            try:
                tag_file = File(file)
            except HeaderNotFoundError as e:
                error(f"Error reading file '{file}': {e}")
                continue
            if tag_file:
                yield Tags(tag_file, file)

def is_valid_path(path: str) -> bool:
    try:
        # Attempt to use the path in a function that raises exceptions for invalid paths
        if not path or path.isspace():
            return False
        os.path.normpath(path)  # Normalizes the path
        return True
    except (ValueError, OSError):
        # Raised for invalid paths or characters
        return False

def sanitize_paths(*paths):
    if not paths:
        raise ValueError("At least one path must be provided.")
    
    # Convert the first path to a Path object (absolute or relative)
    base_path = pathlib.Path(paths[0])
    
    # Ensure subsequent paths are relative and join them
    for sub_path in paths[1:]:
        base_path /= pathlib.Path(sub_path).relative_to(pathlib.Path(sub_path).anchor)  # Remove the anchor if it's absolute
    
    return str(base_path)

def main():
    args = parser.parse_args()

    # Check if the source directory exists
    if not os.path.isdir(args.source):
        error(f"Source directory '{args.source}' does not exist.")
        exit(ExitCodes.SOURCE_DIR_NOT_FOUND)
        return
    
    print(f"Found source directory: {args.source}")
    
    destination = args.destination if args.destination else args.source
    if args.destination:
        if not os.path.isdir(destination):
            error(f"Destination directory '{destination}' does not exist.")
            exit(ExitCodes.DESTINATION_DIR_NOT_FOUND)
            return
        print(f"Found destination directory: {destination}")
    else:
        print(f"Destination directory not specified. Using source directory as destination.")

    discard_dir = args.discard if args.discard else args.source
    if args.discard:
        if not os.path.isdir(args.discard):
            error(f"Discard directory '{args.discard}' does not exist.")
            exit(ExitCodes.DESTINATION_DIR_NOT_FOUND)
            return
        print(f"Found discard directory: {args.discard}")
    else:
        print(f"Discard directory not specified. Discarded files will remain in the source directory.")

    print("Initializing pygame mixer...")
    pygame.mixer.init()

    location_session = PromptSession()

    print("Searching for audio files in source directory...")
    for tags in source_audio_files_generator(args.source):
        print(f"Found audio file: {tags.file_path}")

        pygame.mixer.music.load(tags.file_path)

        history = InMemoryHistory()

        if tags.title:
            history.append_string(tags.title)
        if tags.artist:
            history.append_string(tags.artist)
        if tags.album:
            history.append_string(tags.album)
        if tags.year:
            history.append_string(tags.year)
        if tags.track_number:
            history.append_string(tags.track_number)
        if tags.genre:
            history.append_string(tags.genre)
        if tags.comment:
            history.append_string(tags.comment)
        if tags.album_artist:
            history.append_string(tags.album_artist)
        if tags.composer:
            history.append_string(tags.composer)
        if tags.disc_number:
            history.append_string(tags.disc_number)

        session = PromptSession(history=history)

        new_name = None
        selection = ''
        while selection.lower() not in ['n', 'q', 's', 'dd']:
            # Clear the screen
            os.system('cls' if os.name == 'nt' else 'clear')

            table = Table(title=os.path.basename(tags.file_path))
            table.add_column("Tag", style="cyan")
            table.add_column("Value", style="magenta")

            table.add_row(SelectionOptions.TITLE.value, tags.title)
            table.add_row(SelectionOptions.ARTIST.value, tags.artist)
            table.add_row(SelectionOptions.ALBUM.value, tags.album)
            table.add_row(SelectionOptions.YEAR.value, tags.year)
            table.add_row(SelectionOptions.TRACK_NUMBER.value, tags.track_number)
            table.add_row(SelectionOptions.GENRE.value, tags.genre)
            table.add_row(SelectionOptions.COMMENT.value, tags.comment)
            table.add_row(SelectionOptions.ALBUM_ARTIST.value, tags.album_artist)
            table.add_row(SelectionOptions.COMPOSER.value, tags.composer)
            table.add_row(SelectionOptions.DISC_NUMBER.value, tags.disc_number)

            print(table)
            print(selection_prompt)

            name_parts = []
            if tags.track_number and tags.track_number.isdigit():
                name_parts.append(f'{int(tags.track_number):02d}'.strip())

            if tags.title:
                name_parts.append(tags.title.strip())
            
            if tags.album:
                name_parts.append(tags.album.strip())

            if tags.album_artist:
                name_parts.append(tags.album_artist.strip())

            new_name = ' - '.join(name_parts)

            print(f'New name on (n)ext: [bold green]"{new_name}"[/bold green]')

            selection = Prompt.ask('> ')
            selection_lower = selection.lower()
            if selection_lower == 't':
                tags.title = session.prompt(f'{Id3Tags.TITLE.name}: ', default=tags.title or '')
            elif selection_lower == 'a':
                tags.artist = session.prompt(f'{Id3Tags.ARTIST.name}: ', default=tags.artist or '')
            elif selection_lower == 'l':
                tags.album = session.prompt(f'{Id3Tags.ALBUM.name}: ', default=tags.album or '')
            elif selection_lower == 'y':
                tags.year = session.prompt(f'{Id3Tags.YEAR.name}: ', default=tags.year or '')
            elif selection_lower == 'r':
                tags.track_number = str(IntPrompt.ask(f'{Id3Tags.TRACK_NUMBER.name}: '))
            elif selection_lower == 'g':
                tags.genre = session.prompt(f'{Id3Tags.GENRE.name}: ', default=tags.genre or '')
            elif selection_lower == 'c':
                tags.comment = session.prompt(f'{Id3Tags.COMMENT.name}: ', default=tags.comment or '')
            elif selection_lower == 'b':
                tags.album_artist = session.prompt(f'{Id3Tags.ALBUM_ARTIST.name}: ', default=tags.album_artist or '')
            elif selection_lower == 'm':
                tags.composer = session.prompt(f'{Id3Tags.COMPOSER.name}: ', default=tags.composer or '')
            elif selection_lower == 'i':
                tags.disc_number = str(IntPrompt.ask(f'{Id3Tags.DISC_NUMBER.name}: '))
            elif selection_lower == 'p':
                pygame.mixer.music.play(start=0.0)
            elif selection_lower == 'o':
                pygame.mixer.music.stop()

            elif selection_lower == 'd':
                if Confirm.ask('Are you sure you want to delete this file?', default=False):
                    os.remove(tags.file_path)
                    break

            elif selection_lower == 'n':
                print("Saving tags...")
                tags.save()

        if selection.lower() == 'n' or selection.lower() == 'dd':
            existing_file = pathlib.Path(tags.file_path)

            is_discard = selection.lower() == 'dd'
            
            ext = existing_file.suffix
            
            next_name = new_name if new_name and (existing_file.stem == new_name or Confirm.ask(f'Rename file to "{new_name}{ext}"?', default=True)) else existing_file.stem
            new_file_name = f"{next_name}{ext}"

            if Confirm.ask(f'Move file to {'discard' if is_discard else 'destination'} directory?', default=args.destination is not None or is_discard):
                retry = True
                while retry:
                    if is_discard:
                        default_sub_dir = 'unknown'
                    else:
                        default_sub_dir_parts = []

                        if tags.album_artist and len(tags.album_artist.strip()) > 0:
                            album_artist = tags.album_artist.strip()
                            default_sub_dir_parts.append(album_artist[0])
                            default_sub_dir_parts.append(album_artist)

                        if tags.album and len(tags.album.strip()) > 0:
                            default_sub_dir_parts.append(tags.album.strip())

                        default_sub_dir = os.path.join(*default_sub_dir_parts)

                    sub_dir = location_session.prompt('Enter sub-directory name: ', default=default_sub_dir)
                    if is_valid_path(sub_dir):
                        path = discard_dir if is_discard else destination
                        full_path_dir = sanitize_paths(path, sub_dir)
                        full_path = sanitize_paths(full_path_dir, new_file_name)
                        accept = Confirm.ask(f'Move file from {tags.file_path} to "{full_path}"?', default=True)
                        
                        if accept:
                            os.makedirs(full_path_dir, exist_ok=True)
                            print(f"Moving file from {tags.file_path} to {full_path}")
                            existing_file.rename(full_path)
                            break
                continue

            if existing_file.stem != new_name:
                print(f"Renaming file to {new_file_name} (from {existing_file.name})")
                new_file = existing_file.with_name(new_file_name)
                existing_file.rename(new_file)

        if selection.lower() == 'q':
            print("Bye...")
            exit(0)

if __name__ == '__main__':
    main()