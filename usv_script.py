import json
from playwright.sync_api import sync_playwright, TimeoutError
import re
import time
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load credentials from JSON file with an environment variable fallback for path
config_path = os.getenv("CONFIG_PATH", r"C:\Users\Anurag\Downloads\config.json")
with open(config_path) as config_file:
    config = json.load(config_file)
    username = config["username"]
    password = config["password"]

# Configurable constants for timeout and retry interval
RETRY_INTERVAL = 60  # seconds
PAGE_TIMEOUT = 15000  # ms for page loading
SLEEP_AFTER_SELECT = 10  # seconds for page update after location select
HEADLESS_MODE = True  # Run browser in headless mode for efficiency

def launch_browser_in_incognito(playwright):
    """Launches a new browser in incognito mode"""
    browser = playwright.chromium.launch(headless=HEADLESS_MODE)
    context = browser.new_context()  # Incognito session
    page = context.new_page()
    return browser, context, page

def login(page):
    """Logs into the visa appointment website"""
    try:
        page.goto("https://ais.usvisa-info.com/en-ca/niv/users/sign_in")
        logging.info("Opened login page.")
        page.fill("input[name='user[email]']", username)
        page.fill("input[name='user[password]']", password)
        page.evaluate("document.querySelector('input[name=\"policy_confirmed\"]').click()")
        page.click("input[type='submit'][name='commit']")
        page.wait_for_selector("div.application.attend_appointment.card.success", timeout=PAGE_TIMEOUT)
        logging.info("Successfully logged in.")
    except TimeoutError:
        logging.error("Login page did not load in time.")
        raise
    except Exception as e:
        logging.error(f"Error during login: {e}")
        raise

def navigate_to_appointment(page):
    """Navigates to the appointment page"""
    try:
        continue_button_href = page.get_attribute("a.button.primary.small[href*='continue_actions']", "href")
        appointment_number = re.search(r"/schedule/(\d+)/continue_actions", continue_button_href).group(1)
        appointment_url = f"https://ais.usvisa-info.com/en-ca/niv/schedule/{appointment_number}/appointment"
        page.goto(appointment_url)
        page.wait_for_load_state("load")
        logging.info("Navigated to the appointment scheduling page.")
    except Exception as e:
        logging.error(f"Error navigating to the appointment page: {e}")
        raise

def select_date_and_time(page):
    """Selects the earliest available date and time"""
    try:
        busy_error = page.query_selector("#consulate_date_time_not_available")
        if busy_error and busy_error.is_visible():
            logging.warning("System is busy. No date or time available.")
            return False

        page.click("#appointments_consulate_appointment_date")
        available_date = page.query_selector("#appointments_consulate_appointment_date").get_attribute("value")
        if available_date:
            logging.info(f"Selected available date: {available_date}")
        else:
            logging.warning("No available date found.")
            return False

        time_dropdown = page.query_selector("#appointments_consulate_appointment_time")
        available_times = time_dropdown.query_selector_all("option[value]:not([value=''])")
        if available_times:
            first_available_time = available_times[0].get_attribute("value")
            time_dropdown.select_option(value=first_available_time)
            logging.info(f"Selected available time: {first_available_time}")
        else:
            logging.warning("No available times found.")
            return False

        return True
    except Exception as e:
        logging.error(f"Error selecting date and time: {e}")
        return False

def check_and_reschedule(page):
    """Checks each location for available appointments and reschedules if possible"""
    try:
        for option in page.query_selector_all("#appointments_consulate_appointment_facility_id option[value]"):
            location_name = option.inner_text()
            location_value = option.get_attribute("value")
            page.select_option("#appointments_consulate_appointment_facility_id", value=location_value)
            logging.info(f"Checking location: {location_name}")

            page.wait_for_selector("#appointments_submit", timeout=PAGE_TIMEOUT)
            reschedule_button = page.query_selector("#appointments_submit")
            if reschedule_button and not reschedule_button.is_disabled():
                if select_date_and_time(page):
                    def handle_confirm(dialog):
                        dialog.accept()
                        logging.info("Confirmed the reschedule action.")

                    page.on("dialog", handle_confirm)
                    reschedule_button.click()
                    logging.info(f"Rescheduled successfully at location: {location_name}.")
                    return True

            logging.info(f"No available appointments at {location_name}.")
            time.sleep(SLEEP_AFTER_SELECT)

        logging.info("Cycle completed. Restarting the check for each location.")
        return False
    except Exception as e:
        logging.error(f"Error during location check and reschedule: {e}")
        return False

def login_and_schedule():
    """Main function to perform login and attempt appointment rescheduling"""
    with sync_playwright() as p:
        while True:
            try:
                browser, context, page = launch_browser_in_incognito(p)

                login(page)
                navigate_to_appointment(page)

                if check_and_reschedule(page):
                    logging.info("Appointment successfully rescheduled. Exiting.")
                    break

            except TimeoutError as e:
                logging.error(f"Timeout error: {e}. Retrying in {RETRY_INTERVAL} seconds...")
            except Exception as e:
                logging.error(f"Encountered an error: {e}. Retrying in {RETRY_INTERVAL} seconds...")

            finally:
                if 'context' in locals():
                    context.close()
                if 'browser' in locals():
                    browser.close()
                time.sleep(RETRY_INTERVAL)

# Run the function
login_and_schedule()
