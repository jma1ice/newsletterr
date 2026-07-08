

import logging

logger = logging.getLogger(__name__)

def get_user_display_name(user_id, users_data, display_preference='email'):
    if not users_data:
        return str(user_id)
    
    user = next((u for u in users_data if str(u.get('user_id')) == str(user_id)), None)
    
    if not user:
        return str(user_id)
    
    if display_preference == 'username':
        return user.get('username') or user.get('email') or str(user_id)
    elif display_preference == 'friendly_name':
        return user.get('friendly_name') or user.get('username') or user.get('email') or str(user_id)
    else:
        return user.get('email') or user.get('username') or str(user_id)

def build_enhanced_user_dict(users_data):
    user_dict = {}
    if users_data:
        for user in users_data:
            if user.get('is_active'):
                user_dict[str(user['user_id'])] = {
                    'email': user.get('email', ''),
                    'username': user.get('username', ''),
                    'friendly_name': user.get('friendly_name', ''),
                    'user_id': user.get('user_id')
                }
    return user_dict
