import threading
from flask import Flask

from app.core.config import DB, ADVANCED_ML, log
from app.data.database import db_init, load_hit_rates
from app.core.state import _hit_rate_lock, _hit_rate_cache
from app.web.routes import web_bp

app = Flask(__name__, template_folder='web/templates', static_folder='web/static')
app.config['JSON_AS_ASCII'] = False

# Register routes
app.register_blueprint(web_bp)

def main():
    db_init()
    with _hit_rate_lock:
        _hit_rate_cache.update(load_hit_rates())
    
    # Pre-load league data on a background thread if needed, or wait for first request
    
    log.info(f'NBA Predictor v12.0 [{"ADVANCED ML" if ADVANCED_ML else "STANDARD"}] -> http://localhost:5050')
    app.run(host='0.0.0.0', port=5050, debug=False, threaded=True)

if __name__ == '__main__':
    main()
