import logging
import requests

def send(user_id=None, api_token=None, process=None, subject_format='{executable} process {pid} ended'):
    """


    @param user_id:
    @param api_token:
    @param process:
    @param subject_format:
    """
    payload = {"message": f"{subject_format.format(**process.__dict__)}\n{process.info()}", "user": user_id, "token": api_token}
    try:
        logging.info("Sending pushover notification...")
        r = requests.post('https://api.pushover.net/1/messages.json', data=payload, headers={'User-Agent': 'Python3'})
    except requests.exceptions.RequestException as e:
        logging.error(e)
        return
    if not r.status_code == 200:
        logging.error(r)



