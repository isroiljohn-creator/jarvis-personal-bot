import os
import subprocess
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.obsidian")


def lock_vault(func):
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return func(self, *args, **kwargs)
    return wrapper


class ObsidianVault:
    def __init__(self):
        self.lock = threading.RLock()
        self.repo_url = os.environ.get("OBSIDIAN_REPO_URL")
        self.github_token = os.environ.get("GITHUB_TOKEN")
        if os.path.exists("/app"):
            self.vault_path = Path("/app/obsidian_vault")
        else:
            self.vault_path = Path("/tmp/obsidian_vault")
        
        # Configure git user details
        self.git_name = "Aziza Assistant"
        self.git_email = "aziza@assistant.internal"

    def _get_auth_url(self) -> str:
        if not self.repo_url or not self.github_token:
            return ""
        # Convert https://github.com/user/repo.git to https://<token>@github.com/user/repo.git
        if self.repo_url.startswith("https://"):
            return self.repo_url.replace("https://", f"https://{self.github_token}@")
        return self.repo_url

    def _run_git(self, args: list[str], cwd: Optional[Path] = None) -> str:
        """Executes a git command and returns stdout."""
        try:
            # Set GIT_TERMINAL_PROMPT=0 to prevent hanging on prompts
            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"
            
            res = subprocess.run(
                ["git"] + args,
                cwd=cwd or self.vault_path,
                capture_output=True,
                text=True,
                env=env,
                check=True
            )
            return res.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Git error running {' '.join(args)}: {e.stderr}")
            raise RuntimeError(f"Git command failed: {e.stderr.strip()}")

    def sync(self) -> bool:
        """Syncs local vault clone with GitHub (clones if not exists, pulls otherwise)."""
        auth_url = self._get_auth_url()
        if not auth_url:
            logger.warning("Obsidian credentials or repo url not configured.")
            return False

        try:
            if not self.vault_path.exists():
                logger.info(f"Cloning Obsidian vault from GitHub to {self.vault_path}...")
                # Clone into vault_path
                self.vault_path.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "clone", auth_url, str(self.vault_path)],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                # Configure user name/email locally in this repository
                self._run_git(["config", "user.name", self.git_name])
                self._run_git(["config", "user.email", self.git_email])
                logger.info("Clone completed and user configured.")
            else:
                logger.info("Pulling latest changes for Obsidian vault...")
                self._run_git(["pull"])
            return True
        except Exception as e:
            logger.error(f"Failed to sync Obsidian vault: {e}")
            return False

    @lock_vault
    def add_note(self, filepath: str, content: str, append: bool = False) -> str:
        """Creates or appends a note, commits, and pushes it."""
        if not self.sync():
            return "❌ Obsidian vault is not configured or failed to sync."

        try:
            # Prevent directory traversal
            clean_path = os.path.normpath(filepath).lstrip("/")
            
            # Default to Inbox folder if no subfolder specified and Inbox exists
            if "/" not in clean_path:
                inbox_dir = self.vault_path / "Inbox"
                if inbox_dir.exists():
                    clean_path = f"Inbox/{clean_path}"

            full_path = self.vault_path / clean_path
            
            # Ensure parent directories exist
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            mode = "a" if append else "w"
            with open(full_path, mode, encoding="utf-8") as f:
                f.write(content)
            
            # Add, commit, and push
            self._run_git(["add", clean_path])
            try:
                commit_msg = f"Aziza: {'Updated' if append else 'Created'} note {clean_path}"
                self._run_git(["commit", "-m", commit_msg])
                self._run_git(["push"])
                return f"✅ Qayd muvaffaqiyatli saqlandi: `{clean_path}`"
            except Exception as e:
                # If there's nothing to commit, that's fine
                if "nothing to commit" in str(e):
                    return f"✅ Qayd o'zgarishsiz qoldi: `{clean_path}`"
                raise e
        except Exception as e:
            logger.error(f"Error adding note: {e}")
            return f"❌ Qayd yozishda xatolik: {e}"

    @lock_vault
    def add_file(self, filepath: str, source_path: str) -> str:
        """Copies a file into the vault, commits, and pushes it."""
        if not self.sync():
            return "❌ Obsidian vault is not configured or failed to sync."

        try:
            import shutil
            clean_path = os.path.normpath(filepath).lstrip("/")
            full_path = self.vault_path / clean_path
            
            # Ensure parent directories exist
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.copy2(source_path, full_path)
            
            self._run_git(["add", clean_path])
            try:
                commit_msg = f"Jarvis: Added file {clean_path}"
                self._run_git(["commit", "-m", commit_msg])
                self._run_git(["push"])
                return f"✅ Fayl muvaffaqiyatli saqlandi: `{clean_path}`"
            except Exception as e:
                if "nothing to commit" in str(e):
                    return f"✅ Fayl o'zgarishsiz qoldi: `{clean_path}`"
                raise e
        except Exception as e:
            logger.error(f"Error adding file: {e}")
            return f"❌ Fayl yozishda xatolik: {e}"


    @lock_vault
    def read_note(self, filepath: str) -> str:
        """Pulls and reads a note."""
        if not self.sync():
            return "❌ Obsidian vault is not configured or failed to sync."

        try:
            clean_path = os.path.normpath(filepath).lstrip("/")
            full_path = self.vault_path / clean_path
            
            # Try to read directly, but if not found and it's a simple name, try to look up in Inbox
            if not full_path.exists() and "/" not in clean_path:
                inbox_path = self.vault_path / "Inbox" / clean_path
                if inbox_path.exists():
                    full_path = inbox_path
                    clean_path = f"Inbox/{clean_path}"

            if not full_path.exists():
                return f"❌ Qayd topilmadi: `{clean_path}`"
            
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading note: {e}")
            return f"❌ Qayd o'qishda xatolik: {e}"

    @lock_vault
    def search_notes(self, query: str) -> str:
        """Searches files in the vault."""
        if not self.sync():
            return "❌ Obsidian vault is not configured or failed to sync."

        try:
            # Let's list files recursively or filter by title/query
            notes = []
            for path in self.vault_path.glob("**/*.md"):
                rel_path = path.relative_to(self.vault_path)
                # Check if query matches path or content
                if query.lower() in str(rel_path).lower():
                    notes.append(f"- `{rel_path}`")
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        if query.lower() in f.read().lower():
                            notes.append(f"- `{rel_path}` (matches content)")
                except Exception:
                    pass
            
            if not notes:
                return f"🔍 `{query}` bo'yicha hech qanday qayd topilmadi."
            return "🔍 Topilgan qaydlar:\n" + "\n".join(notes[:20])
        except Exception as e:
            logger.error(f"Error searching notes: {e}")
            return f"❌ Qidiruvda xatolik: {e}"
