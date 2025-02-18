from flask import Flask, request, render_template, redirect, url_for, Response, send_file
import asyncio
import webbrowser
import threading
from threading import Event
import time
import os
from gba_crawler import GBANewsMonitor, CONFIG

app = Flask(__name__)

# Initialize monitor and stop event as None globally
monitor = None
stop_event = None

def run_crawler(keywords, days, cities):
    global monitor, stop_event
    monitor = GBANewsMonitor()
    monitor.configure(keywords, days, cities)
    stop_event = Event()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(monitor.run(stop_event))
    finally:
        loop.close()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        keywords = request.form.get('keywords')
        days = int(request.form.get('days'))
        cities = request.form.getlist('cities')  # Use getlist for multiple selections
        
        # Start crawler in a separate thread
        global stop_event
        stop_event = Event()
        thread = threading.Thread(target=run_crawler, args=(keywords, days, cities))
        thread.start()
        
        # Redirect to progress page
        return redirect(url_for('progress'))
    
    return render_template('index.html')

@app.route('/progress', methods=['GET', 'POST'])
def progress():
    global monitor, stop_event
    
    if request.method == 'POST':
        if 'stop' in request.form:
            stop_event.set()
            monitor.generate_report()
            return redirect(url_for('report'))

    def generate():
        while True:
            if monitor is not None:
                progress_info = f"Processed URLs: {monitor.processed_pages} | Articles Found: {monitor.found_articles}"
                last_url_info = f"Last URL Processed: {monitor.last_processed_url or 'None'}"
                last_article_info = f"Last Article Found: {monitor.last_article_found['title'] if monitor.last_article_found else 'None'}"
                yield f"data: {progress_info} | {last_url_info} | {last_article_info}\n\n"
            time.sleep(1)

    return render_template('progress.html')

@app.route('/report')
def report():
    report_path = os.path.join(CONFIG["storage"]["output_dir"], "report.html")
    if os.path.exists(report_path):
        return send_file(report_path)
    else:
        return "Report not found or not generated yet.", 404

if __name__ == '__main__':
    webbrowser.open('http://127.0.0.1:5000/')
    app.run(debug=True, use_reloader=False)