import pytest
import json
from unittest.mock import AsyncMock, patch, PropertyMock
from bs4 import BeautifulSoup # For parsing HTML

from src.server import get_app # Assuming your Quart app is 'app' in server.py and get_app() returns it
from quart_auth import AuthUser # For login

# Sample config to be returned by the mock
MOCK_SERVER_CONFIG_DATA = {
    "title": "Valheim Test Config",
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Server name", "default": "My Valheim", "value": "Jules Test Server"},
        "port": {"type": "integer", "default": 2456, "value": 2457},
        "world": {"type": "string", "default": "Dedicated", "value": "TestWorld"},
        "password": {"type": "string", "default": "", "value": "secret", "description": "Optional password"},
        "public": {"type": "integer", "enum": [0, 1], "default": 1, "value": 0, "description": "0=private, 1=public"},
        "crossplay": {"type": "boolean", "default": False, "description": "Enable crossplay", "value": True},
        "description_only_field": {"type": "string", "description": "This field only has a description"},
        "default_only_field": {"type": "string", "default": "Default Value", "description": "This field has a default"},
        "boolean_false_field": {"type": "boolean", "default": True, "value": False, "description": "A boolean field that is false"}
    },
    "required": ["name", "port", "world"] 
}
MOCK_SERVER_CONFIG_JSON = json.dumps(MOCK_SERVER_CONFIG_DATA)

@pytest.fixture(name="client")
def _client():
    # Use get_app() to ensure a fresh app instance with its own context for each test
    current_app = get_app() 
    current_app.config['TESTING'] = True
    current_app.config['WTF_CSRF_ENABLED'] = False 
    # Quart-Auth relies on a secret key for session management.
    # It's crucial for testing login/logout and current_user.
    current_app.secret_key = 'test_secret_key_for_auth_in_tests' 
    
    # Ensure Quart-Auth login manager is properly initialized for the test app instance
    # This might be redundant if get_app() already configures extensions,
    # but it's a safeguard for test environments.
    if not hasattr(current_app, 'quart_auth_login_manager') and 'quart_auth' not in current_app.extensions:
         from quart_auth import QuartAuth
         QuartAuth(current_app)
    elif 'quart_auth' in current_app.extensions and not hasattr(current_app, 'quart_auth_login_manager'):
        # If QuartAuth object exists in extensions but manager is not on app
        current_app.quart_auth_login_manager = current_app.extensions['quart_auth']


    return current_app.test_client()

@pytest.mark.asyncio
async def test_configure_route_success_and_data_population(client):
    mock_db_record = {'config': MOCK_SERVER_CONFIG_JSON}

    # Patch current_user. For Quart-Auth, current_user is a proxy.
    # We can patch its underlying `_get_current_object` or mock the proxy behavior.
    # A common way is to patch `quart_auth.current_user` with a PropertyMock that returns our AuthUser.
    # However, patching the direct import in the module (`src.userroutes.current_user`) is often more straightforward.
    with patch('src.userroutes.db.db_select_servers_by_subscription', AsyncMock(return_value=mock_db_record)) as mock_db_call, \
         patch('src.userroutes.current_user', AuthUser("test_user_id")): 

        response = await client.get('/configure?subscription_id=test_sub_id')
        assert response.status_code == 200
        html_content = await response.get_data(as_text=True)
        soup = BeautifulSoup(html_content, 'html.parser')

        mock_db_call.assert_called_once_with('test_sub_id')

        # Check title
        page_title = soup.find('span', id='config-title')
        assert page_title is not None, "Config title span not found"
        assert page_title.string == MOCK_SERVER_CONFIG_DATA['title']
        
        # Check form field population
        
        # Text input: name
        name_input = soup.find('input', {'id': 'name', 'name': 'name'})
        assert name_input is not None, "Name input not found"
        assert name_input.get('type') == 'text'
        assert name_input.get('value') == MOCK_SERVER_CONFIG_DATA["properties"]["name"]["value"]

        # Number input: port
        port_input = soup.find('input', {'id': 'port', 'name': 'port'})
        assert port_input is not None, "Port input not found"
        assert port_input.get('type') == 'number'
        assert port_input.get('value') == str(MOCK_SERVER_CONFIG_DATA["properties"]["port"]["value"])

        # Text input: world
        world_input = soup.find('input', {'id': 'world', 'name': 'world'})
        assert world_input is not None, "World input not found"
        assert world_input.get('type') == 'text'
        assert world_input.get('value') == MOCK_SERVER_CONFIG_DATA["properties"]["world"]["value"]

        # Password input: password
        password_input = soup.find('input', {'id': 'password', 'name': 'password'})
        assert password_input is not None, "Password input not found"
        assert password_input.get('type') == 'password'
        assert password_input.get('value') == MOCK_SERVER_CONFIG_DATA["properties"]["password"]["value"]

        # Number input for integer enum: public
        public_input = soup.find('input', {'id': 'public', 'name': 'public'})
        assert public_input is not None, "Public input not found"
        assert public_input.get('type') == 'number' 
        assert public_input.get('value') == str(MOCK_SERVER_CONFIG_DATA["properties"]["public"]["value"])

        # Checkbox: crossplay
        crossplay_checkbox = soup.find('input', {'id': 'crossplay', 'name': 'crossplay'})
        assert crossplay_checkbox is not None, "Crossplay checkbox not found"
        assert crossplay_checkbox.get('type') == 'checkbox'
        assert crossplay_checkbox.has_attr('checked') == MOCK_SERVER_CONFIG_DATA["properties"]["crossplay"]["value"]

        # Checkbox: boolean_false_field
        boolean_false_checkbox = soup.find('input', {'id': 'boolean_false_field', 'name': 'boolean_false_field'})
        assert boolean_false_checkbox is not None, "boolean_false_field checkbox not found"
        assert boolean_false_checkbox.get('type') == 'checkbox'
        assert boolean_false_checkbox.has_attr('checked') == MOCK_SERVER_CONFIG_DATA["properties"]["boolean_false_field"]["value"]
        
        # Field with description only (should have empty value, no default)
        desc_only_input = soup.find('input', {'id': 'description_only_field', 'name': 'description_only_field'})
        assert desc_only_input is not None, "description_only_field input not found"
        assert desc_only_input.get('value') == '' 

        # Field with default only (should have default value)
        default_only_input = soup.find('input', {'id': 'default_only_field', 'name': 'default_only_field'})
        assert default_only_input is not None, "default_only_field input not found"
        assert default_only_input.get('value') == MOCK_SERVER_CONFIG_DATA["properties"]["default_only_field"]["default"]

        # Check for required attributes (example for 'name')
        assert name_input.has_attr('required')


@pytest.mark.asyncio
async def test_configure_route_no_subscription_id(client):
    with patch('src.userroutes.current_user', AuthUser("test_user_id")):
        response = await client.get('/configure')
        # The route `return []` which Quart cannot process as a response, leading to a TypeError server-side.
        # Quart's default error handling for such unhandled TypeErrors in routes is a 500 Internal Server Error.
        assert response.status_code == 500 


@pytest.mark.asyncio
async def test_configure_route_subscription_not_found(client):
    with patch('src.userroutes.db.db_select_servers_by_subscription', AsyncMock(return_value=None)) as mock_db_call, \
         patch('src.userroutes.current_user', AuthUser("test_user_id")):
        response = await client.get('/configure?subscription_id=not_found_sub_id')
        # Similar to the above, `return []` will cause a 500 Internal Server Error.
        assert response.status_code == 500 
        mock_db_call.assert_called_once_with('not_found_sub_id')

@pytest.mark.asyncio
async def test_configure_route_db_exception_on_select(client):
    # Test how the route handles an unexpected database exception during selection
    with patch('src.userroutes.db.db_select_servers_by_subscription', AsyncMock(side_effect=Exception("DB Select Error"))) as mock_db_call, \
         patch('src.userroutes.current_user', AuthUser("test_user_id")):
        response = await client.get('/configure?subscription_id=test_sub_id_for_db_error')
        # Quart's default error handling should result in a 500 error.
        assert response.status_code == 500
        mock_db_call.assert_called_once_with('test_sub_id_for_db_error')

@pytest.mark.asyncio
async def test_configure_route_invalid_json_in_config_from_db(client):
    # Test scenario where the 'config' field from DB is not valid JSON
    mock_db_record_bad_json = {'config': 'this is definitely not json'}
    with patch('src.userroutes.db.db_select_servers_by_subscription', AsyncMock(return_value=mock_db_record_bad_json)) as mock_db_call, \
         patch('src.userroutes.current_user', AuthUser("test_user_id")):
        response = await client.get('/configure?subscription_id=test_sub_id_bad_json')
        # json.loads() in the route will raise a json.JSONDecodeError. Quart should return 500.
        assert response.status_code == 500
        mock_db_call.assert_called_once_with('test_sub_id_bad_json')

@pytest.mark.asyncio
async def test_configure_route_requires_login(client):
    # Test that accessing /configure without being logged in redirects to login or shows an error
    # This depends on how @login_required is configured. Usually, it redirects.
    # For Quart-Auth, the default is to return a 401 Unauthorized.
    response = await client.get('/configure?subscription_id=some_id')
    assert response.status_code == 401 # Quart-Auth's default for @login_required

# To run these tests:
# 1. Ensure pytest, pytest-asyncio, and beautifulsoup4 are in your project's virtual environment.
#    (pip install pytest pytest-asyncio beautifulsoup4)
# 2. Ensure __init__.py files exist in 'src' and 'src/db' if they are packages.
#    (touch src/__init__.py src/db/__init__.py)
# 3. From the root directory of your project, run: pytest
#
# Key improvements and considerations in this version:
# - Client fixture: Uses get_app() for fresh app instances. Sets a `secret_key` crucial for Quart-Auth session management.
#   Includes a safeguard for QuartAuth initialization, which can be tricky in test contexts.
# - Mocking current_user: `patch('src.userroutes.current_user', AuthUser("test_user_id"))` is used. This is generally effective.
# - HTML Parsing: Uses BeautifulSoup for more reliable and readable assertions on HTML structure and content.
# - Field Checks: More specific checks for input types and values, and for checkbox 'checked' state.
# - Error Handling Tests: Includes tests for database exceptions and invalid JSON data from the DB.
# - Auth Test: Added `test_configure_route_requires_login` to verify @login_required behavior.
# - Status Codes for `return []`: Correctly anticipates 500 errors for routes that `return []` due to Quart's expectation of a Response object.
# - Comments: Added comments for clarity on test setup and choices.
```
