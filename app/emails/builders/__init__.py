# Re-exports so `from app.emails.builders import X` keeps working.
from app.emails.builders.users import get_user_display_name, build_enhanced_user_dict
from app.emails.builders.stats import get_stat_headers, get_stat_cells, build_stats_html_with_cid_background
from app.emails.builders.recently_added import build_recently_added_html_with_cids
from app.emails.builders.cards import build_individual_item_card_html, build_collection_card_html
from app.emails.builders.recommendations import build_recommendations_html_with_cids, _wrapped_ranked_list_html, build_droppedneedle_wrapped_html_with_cids, build_droppedneedle_server_stats_html_with_cids, build_recommendations_section_with_cids
from app.emails.builders.collections import build_collections_html_with_cids

__all__ = [
    "get_user_display_name",
    "build_enhanced_user_dict",
    "get_stat_headers",
    "get_stat_cells",
    "build_stats_html_with_cid_background",
    "build_recently_added_html_with_cids",
    "build_individual_item_card_html",
    "build_collection_card_html",
    "build_recommendations_html_with_cids",
    "_wrapped_ranked_list_html",
    "build_droppedneedle_wrapped_html_with_cids",
    "build_droppedneedle_server_stats_html_with_cids",
    "build_recommendations_section_with_cids",
    "build_collections_html_with_cids",
]
