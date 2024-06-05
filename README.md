# NIHR Leicester BRC Selenium Helper

Helper for Selenium testing and downloading.

## How to Use

### Configuration

This library requires the following environment variables.

- LBRC_SELENIUM_DOWNLOAD_DIRECTORY
  - Directory into which downloads will be saved
- LBRC_SELENIUM_BASE_URL
  - The base URL for the site being accessed.  This is used to convert between relaltive and absolute URLs
- LBRC_SELENIUM_IMPLICIT_WAIT_TIME
  - Time Selenium will wait for elements to appear.  (default: 1s)
- LBRC_SELENIUM_CLICK_WAIT_TIME
  - Time Selenium waits for a page to respond to a click. (default: 1s)
- LBRC_SELENIUM_DOWNLOAD_WAIT_TIME
  - Time selenium waits for a file to download. (default: 30s)
- LBRC_SELENIUM_PAGE_WAIT_TIME
  - Time selenium waits for a page to load. (default: 5s)
- LBRC_SELENIUM_HOST
  - URL of Selenium grid.  If not supplied, Selenium will run locallay.
- LBRC_SELENIUM_PORT
  - Port for Selenium grid (if required). (default: 4444).
- LBRC_SELENIUM_HEADLESS
  - Spefies is Selenium will run in the background if run locally. (default: False)

### Install

In your `requirement.txt` or `requirements.in` file include the line:

```
-e git+https://github.com/LCBRU/lbrc_selenium.git@main#egg=lbrc_selenium
```

### Instantiation

To get an instance of the Selenium, instantiate the helper by calling the
function `get_selenium`.

```
from lbrc_selenium import get_selenium

s = get_selenium()
```

This function will return to you a SeleniumHelper.  If you have defined
the `LBRC_SELENIUM_HOST` environment variable, you will receive a
`SeleniumGridHelper`.  If not, you will received a `SeleniumLocalHelper`.

