"""
Simple Flask Web Server for Journal Scraping
Uses existing scraper modules with a clean web interface
"""

import os
import json
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import uuid
import config

app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

# Create results directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Store active jobs in memory (for simple implementation)
# In production, use Redis or a database
active_jobs = {}

# Load scrapers from config (only enabled ones)
SCRAPERS = {k: v for k, v in config.SCRAPERS.items() if v.get('enabled', True)}


def run_scraper_task(job_id, scraper_type, keyword, start_date, end_date):
    """
    Background task to run the scraper
    This runs in a separate thread to avoid blocking the web server
    """
    try:
        active_jobs[job_id]['status'] = 'running'
        active_jobs[job_id]['start_time'] = datetime.now().isoformat()
        
        # Use the scraper adapter for a clean interface
        from scraper_adapter import run_scraper
        
        output_file = run_scraper(
            job_id=job_id,
            scraper_type=scraper_type,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date
        )
        
        active_jobs[job_id]['status'] = 'completed'
        active_jobs[job_id]['end_time'] = datetime.now().isoformat()
        active_jobs[job_id]['output_file'] = output_file
        active_jobs[job_id]['message'] = 'Scraping completed successfully'
        
    except Exception as e:
        active_jobs[job_id]['status'] = 'failed'
        active_jobs[job_id]['end_time'] = datetime.now().isoformat()
        active_jobs[job_id]['error'] = str(e)
        active_jobs[job_id]['message'] = f'Scraping failed: {str(e)}'


@app.route('/')
def index():
    """Main page with the scraping form"""
    return render_template('index.html', scrapers=SCRAPERS)


@app.route('/api/start-scraping', methods=['POST'])
def start_scraping():
    """
    API endpoint to start a scraping job
    Expected JSON: {
        "scraper": "bmj",
        "keyword": "cancer research",
        "start_date": "01/01/2023",
        "end_date": "12/31/2023"
    }
    """
    try:
        data = request.get_json()
        
        # Validate input
        required_fields = ['scraper', 'keyword', 'start_date', 'end_date']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        scraper_type = data['scraper']
        if scraper_type not in SCRAPERS:
            return jsonify({'error': 'Invalid scraper type'}), 400
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Create job entry
        active_jobs[job_id] = {
            'id': job_id,
            'scraper': scraper_type,
            'scraper_name': SCRAPERS[scraper_type]['name'],
            'keyword': data['keyword'],
            'start_date': data['start_date'],
            'end_date': data['end_date'],
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        }
        
        # Start scraping in background thread
        thread = threading.Thread(
            target=run_scraper_task,
            args=(job_id, scraper_type, data['keyword'], data['start_date'], data['end_date'])
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': 'Scraping job started successfully'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/job-status/<job_id>')
def job_status(job_id):
    """Get the status of a scraping job"""
    if job_id not in active_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(active_jobs[job_id])


@app.route('/api/jobs')
def list_jobs():
    """List all jobs"""
    return jsonify(list(active_jobs.values()))


@app.route('/api/download/<job_id>')
def download_results(job_id):
    """Download the results file for a completed job"""
    if job_id not in active_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = active_jobs[job_id]
    
    if job['status'] != 'completed':
        return jsonify({'error': 'Job not completed yet'}), 400
    
    if 'output_file' not in job or not job['output_file']:
        return jsonify({'error': 'No output file found'}), 404
    
    if not os.path.exists(job['output_file']):
        return jsonify({'error': 'Output file not found on disk'}), 404
    
    return send_file(
        job['output_file'],
        as_attachment=True,
        download_name=os.path.basename(job['output_file'])
    )


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})


if __name__ == '__main__':
    print("=" * 60)
    print("Starting Journal Scraper Web Server...")
    print("=" * 60)
    print(f"\nServer Configuration:")
    print(f"  Host: {config.SERVER_CONFIG['host']}")
    print(f"  Port: {config.SERVER_CONFIG['port']}")
    print(f"  Debug Mode: {config.SERVER_CONFIG['debug']}")
    print(f"\nAccess the application at: http://localhost:{config.SERVER_CONFIG['port']}")
    print("\nAvailable scrapers:")
    for key, scraper in SCRAPERS.items():
        print(f"  ✓ {scraper['name']} ({key})")
    print("\n" + "=" * 60)
    
    app.run(
        debug=config.SERVER_CONFIG['debug'],
        host=config.SERVER_CONFIG['host'],
        port=config.SERVER_CONFIG['port']
    )
