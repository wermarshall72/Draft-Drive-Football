from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
import logging
import secrets

import pygame

from src.application import ApplicationController
from src.audio_settings import (
    SETTINGS_FILE_NAME, AudioSettings, load_audio_settings, save_audio_settings,
)
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_controller import FootballGameController, FootballRunPhase
from src.engine.football_appearance import FootballPlayerAppearance
from src.persistence.run_save import LoadResult, LoadStatus, RunSaveStore, SaveBlocked
from src.profile import ProfileError, TeamProfile, validate_team_name
from src.ui.football_run_screen import ENDED_PHASES, FootballRunScreen
from src.ui.football_ui_kit import match_font, plain_font
from src.ui.football_run_summary import replace_run_summary, run_summary
from src.ui.football_tips import TipState
from src.ui.how_to_play import HowToPlayScreen
from src.ui.layout import LOGICAL_SIZE
from src.ui.main_menu import FootballMainMenuScreen, MenuSaveNotice
from src.ui.main_menu_art import draw_menu_stadium
from src.ui.navigation import ScreenManager
from src.ui.profile_screen import ProfileScreen
from src.ui.screens import GAME_NAME
from src.ui.player_art import draw_draft_player
from src.ui.theme import Theme
from src.ui.volume_slider import AudioBinding

EventSource = Callable[[], Iterable[pygame.event.Event]]
LOGGER = logging.getLogger(__name__)

SAVE_FAILED_NOTICE = "Couldn't save your run. Play on; the game will try again."
RESTORED_NOTICE = MenuSaveNotice(
    "SAVE RESTORED",
    "Your latest save was damaged, so the previous save was restored.",
)
DAMAGED_NOTICE = MenuSaveNotice(
    "SAVED RUN DAMAGED",
    "Your saved run was damaged and could not be loaded. The files were set aside.",
)
NEWER_VERSION_NOTICE = MenuSaveNotice(
    "SAVED BY A NEWER VERSION",
    "Update the game to continue this run, or abandon it to start over.",
    abandonable=True,
)


class DesktopApplication:
    """Resizable, framework-isolated desktop shell around the application boundary."""

    TRANSITION_MS = 260
    def __init__(
        self,
        controller: ApplicationController | None = None,
        *,
        window_size: tuple[int, int] = LOGICAL_SIZE,
        seed_factory: Callable[[], int] | None = None,
        run_store: RunSaveStore | None = None,
    ) -> None:
        self.controller = controller or ApplicationController()
        # The single saved run, kept beside the profile (both in the app-data
        # folder by default); the disk copy is the source of truth across launches.
        self.run_store = run_store or RunSaveStore(Path(self.controller.profile_path).parent)
        self.save_notice: MenuSaveNotice | None = None
        self._save_failure_shown = False
        self.window_size = window_size
        self.seed_factory = seed_factory or (lambda: secrets.randbits(64))
        self.football_controller: FootballGameController | None = None
        self.running = False
        # Music/effects volumes from settings.json beside the profile and run save.
        # Nothing plays sound yet; future audio code reads audio_settings or the gains.
        self.audio_settings: AudioSettings = load_audio_settings(self.settings_path)
        self.audio_binding = AudioBinding(lambda: self.audio_settings, self.update_audio_settings)
        self.profile: TeamProfile | None = None
        self.profile_error: str | None = None
        try:
            self.profile = self.controller.load_profile()
        except ProfileError as error:
            self.profile_error = str(error)

        self.menu_state = (
            self.controller.main_menu_state() if self.profile is not None else None
        )
        self.theme = Theme.from_profile(self.profile)
        self.router = ScreenManager()
        self._transition_started: int | None = None
        team_name = self.profile.team_name if self.profile is not None else "NEW TEAM"
        navigate = self.navigate
        self.menu_screen = FootballMainMenuScreen(
            self.theme,
            self.menu_state,
            self.profile_error,
            navigate,
            self.quit,
            self.start_new_run,
            on_continue_run=self.continue_run,
            run_summary=self.remembered_run_summary,
            save_notice=lambda: self.save_notice,
            on_abandon_save=self.abandon_saved_run,
        )
        self.router.register("main_menu", self.menu_screen)
        self.profile_screen = ProfileScreen(
            self.theme, self.profile, navigate, self.quit, self.save_profile,
            reset_tips=self.reset_tips, audio=self.audio_binding,
        )
        self.router.register("settings", self.profile_screen)
        self.router.register("how_to_play", HowToPlayScreen(self.theme, navigate, self.quit))
        self.tips = TipState(
            self.profile.seen_tips if self.profile is not None else (), self._remember_tip,
        )
        self.run_screen = FootballRunScreen(
            self.theme,
            team_name,
            navigate,
            self.quit,
            on_run_discarded=self._forget_run,
            on_save_point=self.save_run,
            tips=self.tips,
        )
        self.run_screen.pause.audio = self.audio_binding
        self.router.register("football_run", self.run_screen)
        if self.profile is not None:
            self._load_saved_run()
        self.router.show("main_menu")

    def quit(self) -> None:
        """Window close or QUIT: save the run first so it resumes on this decision."""
        self.save_run()
        self.running = False

    # -- audio settings (settings.json) ----------------------------------------------

    @property
    def settings_path(self) -> Path:
        return self.run_store.directory / SETTINGS_FILE_NAME

    @property
    def music_gain(self) -> float:
        """Music volume as 0.0-1.0, for future audio playback."""
        return self.audio_settings.music_gain

    @property
    def effects_gain(self) -> float:
        """Sound-effects volume as 0.0-1.0, for future audio playback."""
        return self.audio_settings.effects_gain

    def update_audio_settings(self, settings: AudioSettings, commit: bool = True) -> None:
        """Settings and the pause AUDIO view: keep the value; ``commit`` also saves it."""
        self.audio_settings = settings
        if not commit:
            return
        try:
            save_audio_settings(settings, self.settings_path)
        except OSError as error:
            # Volumes are a convenience: keep the in-memory value and try again next change.
            LOGGER.warning("Could not save audio settings: %s", error)

    # -- the saved run ---------------------------------------------------------------

    def _load_saved_run(self) -> None:
        try:
            result = self.run_store.load()
        except OSError as error:  # e.g. the data folder itself is unreadable
            LOGGER.warning("Could not check for a saved run: %s", error)
            return
        self._apply_load_result(result)

    def _apply_load_result(self, result: LoadResult) -> None:
        if result.status in (LoadStatus.OK, LoadStatus.RESTORED_FROM_BACKUP):
            controller = result.controller
            assert controller is not None
            if controller.state.phase in ENDED_PHASES:
                self._delete_saved_run()
                return
            self.football_controller = controller
            self.run_screen.team_name = controller.team_name
            self.run_screen.restore(controller)
            if result.status is LoadStatus.RESTORED_FROM_BACKUP:
                self.save_notice = RESTORED_NOTICE
        elif result.status is LoadStatus.DAMAGED:
            self.save_notice = DAMAGED_NOTICE
        elif result.status is LoadStatus.UNSUPPORTED_VERSION:
            self.save_notice = NEWER_VERSION_NOTICE
        elif result.status is LoadStatus.UNSUPPORTED:
            self.save_notice = MenuSaveNotice(
                "SAVED RUN CAN'T BE LOADED",
                f"This version can't continue it ({result.message}). Abandon it to start over.",
                abandonable=True,
            )

    def save_run(self) -> None:
        """Save the current run (or forget it once it has ended); never raises."""
        controller = self.run_screen.controller
        if controller is None:
            return
        if controller.state.phase in ENDED_PHASES:
            self._delete_saved_run()
            return
        try:
            self.run_store.save(controller)
        except (OSError, SaveBlocked, ValueError, TypeError) as error:
            LOGGER.error("Could not save the run: %s", error)
            if not self._save_failure_shown:
                self._save_failure_shown = True
                self.run_screen.show_save_notice(SAVE_FAILED_NOTICE)
            return
        self._save_failure_shown = False

    def _delete_saved_run(self) -> None:
        try:
            self.run_store.delete()
        except OSError as error:
            LOGGER.error("Could not delete the saved run: %s", error)

    def abandon_saved_run(self) -> None:
        """Set an unloadable save aside (the files are kept) so a new run can save."""
        try:
            self.run_store.abandon()
        except OSError as error:
            LOGGER.error("Could not set the saved run aside: %s", error)
            return
        self.save_notice = None

    def navigate(self, screen_id: str) -> None:
        if screen_id == self.router.current_id:
            return
        self.router.show(screen_id)
        if self.running and pygame.display.get_surface() is not None:
            self._transition_started = pygame.time.get_ticks()

    def save_profile(self, name: str, primary: str, secondary: str) -> None:
        if self.profile is None:
            if Path(self.controller.profile_path).exists():
                raise ProfileError(
                    "A profile file already exists. Resolve it outside the game before saving."
                )
            profile = self.controller.create_profile(name, primary, secondary)
        else:
            profile = replace(
                self.profile,
                team_name=validate_team_name(name),
                primary_color_id=primary,
                secondary_color_id=secondary,
            )
            self.controller.save_profile(profile)

        self.profile = profile
        self.profile_error = None
        self.menu_state = self.controller.main_menu_state()
        self.theme = Theme.from_profile(profile)
        self.menu_screen.menu_state = self.menu_state
        self.menu_screen.profile_error = None
        self.menu_screen.theme = self.theme
        self.profile_screen.profile = profile
        self.profile_screen.theme = self.theme
        if not self.run_screen.resumable:
            # A remembered run keeps its own team name; only the colors change.
            self.run_screen.team_name = profile.team_name
        self.run_screen.theme = self.theme
        self.run_screen.match_screen.theme = self.theme
        self.navigate("main_menu")

    # -- one-time tips (remembered in the profile's seen_tips) -----------------------

    def _remember_tip(self, tip_id: str) -> None:
        if self.profile is None or tip_id in self.profile.seen_tips:
            return
        self._store_seen_tips(self.profile.seen_tips + (tip_id,))

    def reset_tips(self) -> None:
        """Settings > SHOW TIPS AGAIN: forget every seen tip so each shows again."""
        self.tips.reset_seen()
        if self.profile is not None:
            self._store_seen_tips(())

    def _store_seen_tips(self, seen: tuple[str, ...]) -> None:
        assert self.profile is not None
        profile = replace(self.profile, seen_tips=seen)
        try:
            self.controller.save_profile(profile)
        except (OSError, ProfileError) as error:
            # Tips are a convenience; a failed save only means a tip may show again.
            LOGGER.warning("Could not save seen tips: %s", error)
            return
        self.profile = profile
        self.profile_screen.profile = profile
        if self.menu_state is not None:
            self.menu_state = replace(self.menu_state, profile=profile)
            self.menu_screen.menu_state = self.menu_state

    def start_new_run(self, difficulty: FootballAIDifficulty) -> None:
        if self.menu_state is None:
            raise RuntimeError("A saved team profile is required to start a run.")
        builder_seed, shop_seed, ai_seed, match_seed = (
            self.seed_factory() for _ in range(4)
        )
        football_controller = FootballGameController(
            self.menu_state.profile.team_name,
            difficulty=difficulty,
            builder_seed=builder_seed,
            shop_seed=shop_seed,
            ai_seed=ai_seed,
            match_seed=match_seed,
            team_primary_color_id=self.menu_state.profile.primary_color_id,
        )
        if self.run_store.blocked:
            # The replace-run confirmation covered the unloadable save.
            self.abandon_saved_run()
        self.football_controller = football_controller
        self.save_notice = None
        self.run_screen.team_name = self.menu_state.profile.team_name
        self.run_screen.begin(football_controller)
        self.save_run()  # the new run replaces the saved one
        self.navigate("football_run")

    def remembered_run_summary(self) -> tuple[str, str] | None:
        """(menu summary, replace-warning summary) for a resumable run, else None."""
        if not self.run_screen.resumable:
            return None
        state = self.run_screen.controller.state
        return run_summary(state), replace_run_summary(state)

    def continue_run(self) -> None:
        if not self.run_screen.resumable:
            raise RuntimeError("There is no run to continue.")
        self.run_screen.resume()
        self.navigate("football_run")

    def _forget_run(self) -> None:
        """QUIT RUN or leaving an ended run: it is gone from memory and disk."""
        self.football_controller = None
        self._delete_saved_run()

    def run(self, event_source: EventSource | None = None) -> None:
        pygame.init()
        try:
            pygame.display.set_caption(GAME_NAME)
            window = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
            pygame.key.start_text_input()
            canvas = pygame.Surface(LOGICAL_SIZE)
            clock = pygame.time.Clock()
            self.running = True
            source = pygame.event.get if event_source is None else event_source
            self.router.draw(canvas)
            while self.running:
                for event in source():
                    if event.type == pygame.QUIT:
                        self.quit()
                    elif event.type == pygame.VIDEORESIZE:
                        self.window_size = (max(1, event.w), max(1, event.h))
                        window = pygame.display.set_mode(
                            self.window_size, pygame.RESIZABLE
                        )
                    elif not self._transition_is_active(pygame.time.get_ticks()):
                        active_screen = self.router.current_id
                        self.router.handle_event(self._logical_event(event))
                        if self.router.current_id != active_screen:
                            self.router.draw(canvas)

                if not self.running:
                    break
                self.router.draw(canvas)
                now = pygame.time.get_ticks()
                self._draw_transition(canvas, now)
                menu_overlay = (
                    self.menu_screen.overlay
                    if self.router.current_id == "main_menu"
                    and not self._transition_is_active(now)
                    else None
                )
                self._present(
                    canvas, window, menu_overlay=menu_overlay, theme=self.theme,
                    portraits=(
                        self.run_screen.player_inspection.portraits
                        if self.router.current_id == "football_run"
                        and self.run_screen.state is not None
                        and self.run_screen.state.phase is FootballRunPhase.PLAYER_DRAFT
                        and not self.run_screen.pause_open
                        and not self._transition_is_active(now)
                        else ()
                    ),
                )
                clock.tick(60)
        finally:
            self.running = False
            # Cached fonts die with the font module; drop them so a later init rebuilds them.
            match_font.cache_clear()
            plain_font.cache_clear()
            pygame.quit()

    def _logical_event(self, event: pygame.event.Event) -> pygame.event.Event:
        if event.type not in (
            pygame.MOUSEMOTION,
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
        ):
            return event
        logical_width, logical_height = LOGICAL_SIZE
        window_width, window_height = self.window_size
        scale = min(window_width / logical_width, window_height / logical_height)
        rendered_width = round(logical_width * scale)
        rendered_height = round(logical_height * scale)
        offset_x = (window_width - rendered_width) // 2
        offset_y = (window_height - rendered_height) // 2
        physical_x, physical_y = event.pos
        position = (
            round((physical_x - offset_x) / scale),
            round((physical_y - offset_y) / scale),
        )
        return pygame.event.Event(event.type, {**event.dict, "pos": position})

    def _transition_is_active(self, now: int) -> bool:
        if self._transition_started is None:
            return False
        if now - self._transition_started >= self.TRANSITION_MS:
            self._transition_started = None
            return False
        return True

    def _draw_transition(self, canvas: pygame.Surface, now: int) -> None:
        if not self._transition_is_active(now):
            return

        assert self._transition_started is not None
        elapsed = (now - self._transition_started) / self.TRANSITION_MS
        progress = min(1.0, max(0.0, elapsed))
        eased = progress * progress * (3 - 2 * progress)
        width, height = canvas.get_size()
        cover_width = round(width * (1 - eased))
        if cover_width <= 0:
            return

        curtain = pygame.Surface((cover_width, height))
        for y in range(0, height, 4):
            position = y / max(1, height - 1)
            if position < 0.5:
                color = _mix_color(
                    self.theme.canvas_lift,
                    self.theme.canvas,
                    position * 2,
                )
            else:
                color = _mix_color(
                    self.theme.canvas,
                    self.theme.primary_dark,
                    (position - 0.5) * 2,
                )
            pygame.draw.line(curtain, color, (0, y), (cover_width, y), 4)

        fieldline_color = self.theme.border_soft
        for fraction in (0.23, 0.77):
            y = round(height * fraction)
            pygame.draw.line(
                curtain,
                (*fieldline_color[:3], 110),
                (0, y),
                (cover_width, y),
                1,
            )
        for x_fraction in (0.2, 0.4, 0.6, 0.8):
            x = round(width * x_fraction)
            if x < cover_width:
                pygame.draw.line(
                    curtain,
                    fieldline_color,
                    (x, 0),
                    (x, height),
                    1,
                )

        canvas.blit(curtain, (0, 0))
        edge = cover_width - 1
        for distance in range(min(10, cover_width)):
            alpha = round(50 * (1 - distance / 10))
            pygame.draw.line(
                canvas,
                (*self.theme.primary_accent[:3], alpha),
                (edge - distance, 0),
                (edge - distance, height),
                1,
            )
        pygame.draw.line(
            canvas,
            self.theme.secondary_accent,
            (edge, 0),
            (edge, height),
            1,
        )

    @staticmethod
    def _present(
        canvas: pygame.Surface, window: pygame.Surface, *,
        menu_overlay: pygame.Surface | None = None, theme: Theme | None = None,
        portraits: Iterable[tuple[pygame.Rect, FootballPlayerAppearance, bool]] = (),
    ) -> None:
        window.fill((0, 0, 0))
        logical_width, logical_height = LOGICAL_SIZE
        window_width, window_height = window.get_size()
        scale = min(window_width / logical_width, window_height / logical_height)
        size = (
            max(1, round(logical_width * scale)),
            max(1, round(logical_height * scale)),
        )
        if menu_overlay is not None:
            if theme is None:
                raise ValueError("A theme is required to present the menu.")
            scaled = pygame.Surface(size)
            draw_menu_stadium(scaled, theme.primary, theme.secondary)
            scaled.blit(pygame.transform.smoothscale(menu_overlay, size), (0, 0))
        else:
            scaled = pygame.transform.smoothscale(canvas, size)
            for rect, appearance, active in portraits:
                portrait = pygame.Rect(
                    round(rect.left * scale), round(rect.top * scale),
                    round(rect.width * scale), round(rect.height * scale),
                )
                pygame.draw.rect(scaled, "#13283b", portrait)
                draw_draft_player(scaled, portrait, appearance, active)
        window.blit(
            scaled,
            ((window_width - size[0]) // 2, (window_height - size[1]) // 2),
        )
        pygame.display.flip()


def _mix_color(
    first: pygame.Color, second: pygame.Color, amount: float
) -> pygame.Color:
    return pygame.Color(
        round(first.r + (second.r - first.r) * amount),
        round(first.g + (second.g - first.g) * amount),
        round(first.b + (second.b - first.b) * amount),
    )
