import traceback
from app.services.predict_service import predict_player
try:
    print(predict_player(2544, 'LeBron James', 'LAL', 'DEN', True, '2026-03-25', 'F'))
except Exception as e:
    traceback.print_exc()
