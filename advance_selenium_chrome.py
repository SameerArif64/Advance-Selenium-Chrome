from time import sleep
from subprocess import Popen
from pathlib import Path
from psutil import process_iter, Process
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from typing import Callable, Literal, Optional
from selenium.webdriver.remote.webelement import WebElement
from win32process import GetWindowThreadProcessId
from pygetwindow import getAllWindows
import requests
from concurrent.futures import ThreadPoolExecutor


class AdvanceSeleniumChrome(webdriver.Chrome):
    """
    A custom Selenium Chrome WebDriver class with additional functionalities such as remote debugging, 
    handling crashed tabs, and various element interaction methods.

    Args:
        driver (Optional[webdriver.Chrome]): An existing Chrome WebDriver instance to use.
        remote_debugging_port (Optional[int]): Port for remote debugging.
        headless (bool): Whether to run Chrome in headless mode.
        download_directory (Optional[Path]): Directory to save downloaded files.
        proxy_url (Optional[str]): Proxy server URL.
        extension_path (Optional[Path]): Path to a Chrome extension to load.
        chrome_options (Options): Chrome options to configure the browser.
        user_data_dir (Optional[Path]): Directory for user data.
        chrome_driver_path (Path): Path to the ChromeDriver executable.
        debug (bool): Whether to enable debug logging.
    """
    def __init__(
        self,
        driver                  : Optional[webdriver.Chrome]    = None,
        remote_debugging_port   : Optional[int]                 = None,
        headless                : bool                          = False,
        download_directory      : Optional[Path]                = None,
        proxy_url               : Optional[str]                 = None,
        extension_path          : Optional[Path]                = None,
        chrome_options          : Options                       = None,
        user_data_dir           : Optional[Path]                = None,
        chrome_driver_path      : Path                          = Path(ChromeDriverManager().install()),
        debug                   : bool                          = False
    ):
        
        self.CHROME_PATH            = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.remote_debugging_port  = remote_debugging_port
        self.user_data_dir          = user_data_dir
        self.debug                  = debug
        self.browser_pid            = None
        self.logging_string         = ""


        if driver:
            # Replace attributes of the current instance with those of the passed driver
            self.__dict__.update(driver.__dict__)
            # Extract remote debugging ports from driver capabilities
            debugger_address = self.capabilities.get('goog:chromeOptions', {}).get('debuggerAddress')
            self.remote_debugging_port = int(debugger_address.split(":")[-1]) if debugger_address else None
            if self.remote_debugging_port in range(53000, 54000):
                self.remote_debugging_port = None
            self.bring_to_front()
            print("Initialized Existing Chrome WebDriver", end='') if self.debug else None
        else:
            # Initialize the base class (webdriver.Chrome) with the configured options
            service = Service(chrome_driver_path)
            # Prepare Chrome options
            options = chrome_options or Options()
            if self.remote_debugging_port:
                if not self.user_data_dir:
                    self.user_data_dir = Path(f"C:/ChromeRemoteDebug/{self.remote_debugging_port}")
                if not self._get_pid_using_remote_debugging_chrome():
                    self._launch_debugging_chrome()
                else:
                    self._detect_and_handle_crashed_tabs()
                    self.bring_to_front()
                options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.remote_debugging_port}")
            else:
                if headless:
                    options.add_argument("--headless=new")  # New headless mode for better compatibility
                    options.add_argument("--disable-gpu")
                    options.add_argument("--no-sandbox")
                    options.add_argument("--disable-dev-shm-usage")
                    options.add_argument("--profile-directory=Default")
                if download_directory:
                    prefs = {
                        "download.default_directory": str(download_directory),
                        "download.directory_upgrade": True,
                        "download.prompt_for_download": False,
                    }
                    options.add_experimental_option("prefs", prefs)
                if proxy_url:
                    options.add_argument(f'--proxy-server={proxy_url}')
                if extension_path and extension_path.exists():
                    options.add_extension(str(extension_path))
                if self.user_data_dir:
                    options.add_argument(fr"--user-data-dir={user_data_dir}")

            super().__init__(service=service, options=options)
            print("Initialized New Chrome WebDriver", end='') if self.debug else None

        if self.remote_debugging_port:
            self.logging_string = f" with debugging port: {self.remote_debugging_port}"
        print(self.logging_string) if self.debug else None
      
        
    def _get_debugger_tabs(self):
        """Fetches all tabs from the remote debugging Chrome instance."""
        try:
            response = requests.get(f'http://localhost:{self.remote_debugging_port}/json')
            return response.json()
        except requests.exceptions.RequestException:
            print("Could not connect to remote debugger.")
            return []

    def _is_crashed_tab(self, tab):
        """Determines if a tab is in an 'Aw Snap' or Out of Memory state."""
        ws_url = tab.get('webSocketDebuggerUrl', '')
        if not ws_url:
            return False
        try:
            response = requests.get(ws_url.replace("ws://", "http://").replace("/devtools/page/", "/json/page/"))
            return 'error' in response.text.lower() or 'out of memory' in response.text.lower()
        except requests.exceptions.RequestException:
            return False

    def _handle_crashed_tab(self, tab):
        """Handles crashed tabs by reopening and closing them."""
        if self._is_crashed_tab(tab):
            print(f"Crashed tab detected: {tab['title']}")
            new_tab = self.execute_cdp_cmd("Target.createTarget", {"url": tab['url']})
            print(f"Opened new tab with URL: {tab['url']}") if self.debug else None
            self.execute_cdp_cmd("Target.closeTarget", {"targetId": tab['id']})
            print("Closed crashed tab.") if self.debug else None

    def _detect_and_handle_crashed_tabs(self):
        """Detects crashed tabs and handles them in parallel."""
        tabs = self._get_debugger_tabs()
        with ThreadPoolExecutor() as executor:
            executor.map(lambda tab: self._handle_crashed_tab(tab), tabs)

    def _launch_debugging_chrome(self):
        """Launch Chrome with remote debugging enabled."""
        if not self.user_data_dir.exists():
            self.user_data_dir.mkdir(parents=True, exist_ok=True)
        Popen([self.CHROME_PATH, f'--remote-debugging-port={self.remote_debugging_port}', f'--user-data-dir={self.user_data_dir}'])
        # print(f"Launched Chrome with remote debugging on port {self.remote_debugging_port}.")

    def _get_pid_using_remote_debugging_chrome(self) -> Optional[int]:
        """Check if Chrome is running with the specified remote debugging port and return its PID."""
        for proc in process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'].lower() == "chrome.exe" and \
                   f"--remote-debugging-port={self.remote_debugging_port}" in " ".join(proc.info['cmdline']).lower():
                    return proc.info['pid']
            except (AttributeError, KeyError):
                continue
        return None


    def bring_to_front(self):
        """Activate the Chrome window to bring it to front."""
        if self.browser_pid is None:
            if self.remote_debugging_port:
                self.browser_pid = self._get_pid_using_remote_debugging_chrome()
            else:
                self.browser_pid = next(child.pid for child in Process(self.service.process.pid).children() if child.name().lower() == "chrome.exe")

        if self.browser_pid is None:
            raise RuntimeError(f"No Chrome process found{self.logging_string}.")

        chrome_windows = [window for window in getAllWindows() if 'chrome' in window.title.lower()]
        for window in chrome_windows:
            try:
                hwnd = window._hWnd
                if hwnd:
                    _, window_pid = GetWindowThreadProcessId(hwnd)
                    if window_pid == self.browser_pid or self.browser_pid in [child.pid for child in Process(window_pid).children()]:
                        if not window.isMinimized:
                            window.minimize()
                        window.restore()
                        window.activate()
                        # print(f"Activated Chrome window: {window.title}")
                        return
            except Exception as e:
                print(f"Error activating window: {e}")
        raise RuntimeError(f"No Open Chrome window found{self.logging_string}.")

    def switch_to_tab_with_url(self, target_url: str, new_tab_url: str = None):
        """
        Switches to an existing tab with the specified target URL or opens a new tab with the provided URL.
        This function first checks if the current tab's URL matches the target URL. If it does, it remains on the current tab.
        If not, it iterates through all open tabs to find one with the target URL and switches to it. If no such tab is found,
        it looks for an empty tab (e.g., a new tab page) to reuse. If an empty tab is found, it navigates to the new_tab_url
        (or target_url if new_tab_url is not provided). If no empty tab is found, it opens a new tab with the new_tab_url
        (or target_url if new_tab_url is not provided).
        Args:
            target_url (str): The URL to switch to or open in a new tab.
            new_tab_url (str, optional): The URL to open in a new tab if no tab with the target URL is found. Defaults to None.
        Returns:
            None
        """
        if self.current_url and target_url in self.current_url:
            print("Already at tab having URL:", self.current_url) if self.debug else None
            return
        
        empty_tab_handle = None
        for handle in self.window_handles:
            self.switch_to.window(handle)
            if target_url in self.current_url:
                print("Switched to tab with URL:", self.current_url) if self.debug else None
                return
            if self.current_url in ['data:,', 'chrome://new-tab-page/']:
                empty_tab_handle = handle
        else:
            print(f"No tab found with URL: {target_url}") if self.debug or not new_tab_url else None
        # If no tab found, search for empty tab or open a new tab
        if new_tab_url:
            if empty_tab_handle:
                print(f"An empty tab exists, opening '{new_tab_url}' in it.") if self.debug else None
                self.switch_to.window(handle)
                self.get(new_tab_url)
            else:
                print(f"Opening a new tab with the URL: {new_tab_url}.") if self.debug else None
                self.execute_cdp_cmd("Target.createTarget", {"url": new_tab_url})
                self.switch_to.window(self.window_handles[-1])  # Switch to the newly opened tab
    
    def _retry_logic(self, action: Callable[[], WebElement], retries: int = 2, suppress_error: bool = False) -> Optional[WebElement]:
        """
        Retry logic for executing actions with suppress_error option.

        Args:
            action (Callable[[], WebElement]): The action to perform as a callable function.
            retries (int): Number of retries. Default is 2.
            suppress_error (bool): Whether to suppress exceptions. Default is False.

        Returns:
            WebElement or None: The result of the action if successful, or None if suppressed and failed.

        Raises:
            Exception: The last caught exception if all attempts fail and suppress_error is False.
        """
        for _ in range(retries):
            try:
                return action()
            except Exception as e:
                if suppress_error:
                    return None
                sleep(1)
                error = e
        raise error  # Raise the last caught exception if suppress_error is False

    def wait_for_element(self, selector: str, by: str = By.XPATH, timeout: int = 120, condition: str = "visible", suppress_error: bool = False) -> Optional[WebElement]:
        """
        Wait for an element to meet the specified condition.

        Returns:
            WebElement or None: The located element if the condition is met, or None if suppressed and failed.
        """
        conditions = {
            "visible": EC.visibility_of_element_located,
            "clickable": EC.element_to_be_clickable,
            "present": EC.presence_of_element_located,
        }

        if condition not in conditions:
            raise ValueError(f"Unsupported condition '{condition}'. Choose from 'visible', 'clickable', or 'present'.")

        wait_condition = conditions[condition]((by, selector))

        def action() -> WebElement:
            return WebDriverWait(self, timeout).until(wait_condition)

        return self._retry_logic(action, retries=1, suppress_error=suppress_error)

    def click_element(self, selector: str, by: str = By.XPATH, parent_element: Optional[WebElement] = None, immediate: bool = False, timeout: int = 15, suppress_error: bool = False, retries: int = 2) -> Optional[WebElement]:
        """
        Click on an element with retry logic.

        Args:
            selector (str): The selector to locate the element.
            by (str): The method to locate the element (default is By.XPATH).
            parent_element (Optional[WebElement]): The parent element to search within (default is None).
            immediate (bool): Whether to click immediately without waiting (default is False).
            timeout (int): The maximum time to wait for the element to be clickable (default is 15 seconds).
            suppress_error (bool): Whether to suppress exceptions (default is False).
            retries (int): The number of retries if the action fails (default is 2).

        Returns:
            WebElement or None: The clicked element if successful, or None if suppressed and failed.
        """
        def action() -> WebElement:
            search_context = parent_element or self
            if immediate:
                element = search_context.find_element(by=by, value=selector)
            else:
                element = WebDriverWait(search_context, timeout).until(EC.element_to_be_clickable((by, selector)))
            ActionChains(self).click(element).perform()
            return element

        return self._retry_logic(action, retries=retries, suppress_error=suppress_error)

    def double_click_element(self, selector: str, by: str = By.XPATH, timeout: int = 15, parent_element: Optional[WebElement] = None, suppress_error: bool = False, retries: int = 2) -> Optional[WebElement]:
        """
        Double-click on a web element specified by the selector with retry logic.
        Args:
            selector (str): The selector string to locate the element.
            by (str, optional): The type of selector to use (e.g., By.XPATH, By.ID). Defaults to By.XPATH.
            timeout (int, optional): The maximum time to wait for the element to be clickable. Defaults to 15 seconds.
            parent_element (Optional[WebElement], optional): The parent element to search within. Defaults to None.
            suppress_error (bool, optional): If True, suppresses exceptions and returns None on failure. Defaults to False.
            retries (int, optional): The number of retry attempts if the action fails. Defaults to 2.
            Optional[WebElement]: The double-clicked element if successful, or None if suppressed and failed.
        Returns:
            WebElement or None: The double-clicked element if successful, or None if suppressed and failed.
        """
        def action() -> WebElement:
            search_context = parent_element or self
            element = WebDriverWait(search_context, timeout).until(EC.element_to_be_clickable((by, selector)))
            ActionChains(self).double_click(element).perform()
            return element

        return self._retry_logic(action, retries=retries, suppress_error=suppress_error)

    def send_keys_to_element(self, selector: str, key, by: str = By.XPATH, timeout: int = 15, parent_element: Optional[WebElement] = None, suppress_error: bool = False, retries: int = 2) -> Optional[WebElement]:
        """
        Send keys to a web element identified by a selector with retry logic.
        Args:
            selector (str): The selector string to locate the element.
            key: The key(s) to send to the element.
            by (str, optional): The method to locate elements (default is By.XPATH).
            timeout (int, optional): The maximum time to wait for the element to be present (default is 15 seconds).
            parent_element (Optional[WebElement], optional): The parent element to search within, if any (default is None).
            suppress_error (bool, optional): Whether to suppress errors if the action fails (default is False).
            retries (int, optional): The number of retry attempts if the action fails (default is 2).
            Optional[WebElement]: The element after sending keys if successful, or None if suppressed and failed.
        Returns:
            WebElement or None: The element after sending keys if successful, or None if suppressed and failed.
        """
        def action() -> WebElement:
            search_context = parent_element or self
            element = WebDriverWait(search_context, timeout).until(EC.presence_of_element_located((by, selector)))
            element.send_keys(key)
            return element

        return self._retry_logic(action, retries=retries, suppress_error=suppress_error)

    def select_value(self, selector: str, value, by: str = By.XPATH, timeout: int = 15, select_by: Literal["index", "value", "visible text"] = "value", parent_element: Optional[WebElement] = None, suppress_error: bool = False, retries: int = 2) -> Optional[WebElement]:
        """
        Select a value from a dropdown element with retry logic.
        Args:
            selector (str): The selector string to locate the dropdown element.
            value: The value to select in the dropdown. The type depends on `select_by`.
            by (str, optional): The method to locate the element (default is By.XPATH).
            timeout (int, optional): The maximum time to wait for the element to be present (default is 15 seconds).
            select_by (Literal["index", "value", "visible text"], optional): The method to select the value in the dropdown (default is "value").
            parent_element (Optional[WebElement], optional): The parent element to search within, if any (default is None).
            suppress_error (bool, optional): Whether to suppress errors and return None if selection fails (default is False).
            retries (int, optional): The number of retries to attempt if selection fails (default is 2).
            Optional[WebElement]: The dropdown element after selection if successful, or None if suppressed and failed.
        Raises:
            ValueError: If `select_by` is not one of "index", "value", or "visible text".
        Returns:
            WebElement or None: The dropdown element after selection if successful, or None if suppressed and failed.
        """
        if select_by not in ["index", "value", "visible text"]:
            raise ValueError(f"Invalid `select_by` value: {select_by}")
        
        def action() -> WebElement:
            search_context = parent_element or self
            element = WebDriverWait(search_context, timeout).until(EC.presence_of_element_located((by, selector)))
            dropdown = Select(element)
            if select_by == "index":
                dropdown.select_by_index(value)
            elif select_by == "value":
                dropdown.select_by_value(value)
            elif select_by == "visible text":
                dropdown.select_by_visible_text(value)
            return element

        return self._retry_logic(action, retries=retries, suppress_error=suppress_error)

    def scroll(self, move: Literal["Top", "Up", "Down", "Bottom"]) -> None:
        """
        Scroll the webpage in the specified direction.

        Args:
            move (Literal["Top", "Up", "Down", "Bottom"]): Direction to scroll.
                "Top" to scroll to the top of the page.
                "Up" to scroll up by a fixed amount (250 pixels).
                "Down" to scroll down by a fixed amount (250 pixels).
                "Bottom" to scroll to the bottom of the page.
        """
        if move == "Top":
            self.execute_script("window.scrollTo(0, 0);")
        elif move == "Up":
            self.execute_script("window.scrollBy(0, -250);")
        elif move == "Down":
            self.execute_script("window.scrollBy(0, 250);")
        elif move == "Bottom":
            self.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        else:
            raise ValueError("Invalid value for move. Use 'Up', 'Down', 'Top' or 'Bottom'.")