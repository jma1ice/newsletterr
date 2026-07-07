import os, math, uuid, base64, smtplib, sqlite3, requests, time, threading, re, json, mimetypes, shutil, calendar, traceback, io, sys, secrets, html, bleach
from collections import defaultdict
from cryptography.fernet import Fernet, InvalidToken
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv, set_key, find_dotenv
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid, formataddr
from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, session, abort, make_response
from functools import wraps
from pathlib import Path
from PIL import Image, ImageFilter, ImageEnhance
from playwright.sync_api import sync_playwright
from plex_api_client import PlexAPI
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs, urlencode, quote

from app import config, state
from app.crypto import encrypt, decrypt
from app.blueprints.auth import login, logout
from app.blueprints.main import index, proxy_art, proxy_img, about, clear_cache_route, cache_status
from app.blueprints.stats import pull_stats, pull_recommendations, pull_droppedneedle_stats, fetch_collections, get_collection_items
from app.blueprints.api import test_tautulli, test_conjurr, test_droppedneedle, gif_search, plex_create_pin, plex_poll_pin, plex_get_info
from app.blueprints.scheduling import scheduling, create_schedule, update_schedule, delete_schedule, send_schedule_now, toggle_schedule, preview_schedule, preview_schedule_page, get_calendar_data
from app.blueprints.emails import send_email, email_history, clear_email_history, get_email_recipients, get_email_lists, save_email_list_route, delete_email_list_route, get_email_templates, save_email_template, delete_email_template
from app.blueprints.settings import settings, upload_logo, delete_logo, upload_media
from app.scheduler import start_background_workers, background_scheduler, refresh_daily_cache
from app.hooks import inject_update_info, refresh_hsts_setting, set_security_headers
from app.emails.images import fetch_and_attach_image, fetch_and_attach_blurred_image, fetch_and_attach_small_thumbnail, truncate_text
from app.emails.blocks import build_graph_html_with_frontend_image, build_text_block_html, build_separator_html, build_image_html_with_cid, build_emoji_html
from app.emails.fetchers import fetch_tautulli_data_for_email, fetch_recent_data_for_index, get_current_tautulli_data_for_email, get_recommendations_for_users, get_droppedneedle_wrapped_for_users, get_droppedneedle_server_stats_cached
from app.emails.builders import get_user_display_name, build_enhanced_user_dict, get_stat_headers, get_stat_cells, build_stats_html_with_cid_background, build_recently_added_html_with_cids, build_recommendations_html_with_cids, _wrapped_ranked_list_html, build_droppedneedle_wrapped_html_with_cids, build_droppedneedle_server_stats_html_with_cids, build_recommendations_section_with_cids, build_individual_item_card_html, build_collection_card_html, build_collections_html_with_cids
from app.emails.assemble import convert_html_to_plain_text, attach_logo_image, build_email_html_with_all_cids, build_complete_email_html_with_cid_logo
from app.emails.send import group_recipients_by_user, send_standard_email_with_cids, send_recommendations_email_with_cids, send_single_user_email_with_cids
from app.render import capture_chart_images_via_headless
from app.emails.scheduled import send_scheduled_email, send_scheduled_email_with_cids, send_scheduled_user_email_with_cids, send_scheduled_single_email_with_cids
from app.clients.tautulli import run_tautulli_command
from app.clients.plex import get_plex_client_identifier, get_plex_headers, get_plex_machine_id, build_plex_web_link, search_plex_for_rating_key, fetch_tv_shows_from_plex_sdk, fetch_movies_from_plex_sdk, fetch_albums_from_plex_sdk, fetch_recently_added_using_plex_sdk, get_collection_items_for_email
from app.clients.conjurr import run_conjurr_command
from app.clients.droppedneedle import fetch_droppedneedle_users, run_droppedneedle_command, fetch_droppedneedle_server_stats
from app.clients.github import _norm, _check_github_latest, _ensure_recent_check, _background_update_checker
from app.cache import get_global_cache_status, can_use_cached_data_for_preview, is_cache_valid, get_cached_data, set_cached_data, get_cache_info, clear_cache, gkak
from app.db import init_db, migrate_data_from_separate_dbs, migrate_schema, migrate_musicseerr_to_droppedneedle, migrate_ra_recs_to_recently_added_recommendations, migrate_email_templates_for_expanded_collections, migrate_email_templates_for_header_title, migrate_email_templates_for_custom_html
from app.security import require_csrf_for_json, sanitize_html_input, escape_html_output, requires_auth, check_credentials, safe_get, sanitize_html
from app.theme import get_theme_settings, get_email_theme_colors, build_email_css_from_theme
from app.store import get_saved_email_lists, save_email_list, delete_email_list, get_email_schedules, calculate_next_send, create_email_schedule, update_email_schedule, delete_email_schedule, toggle_schedule_status, update_schedule_last_sent

app = Flask(__name__, template_folder = str(config.ASSET_ROOT / 'templates'), static_folder = str(config.ASSET_ROOT / 'static'))


