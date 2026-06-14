import json
import os
from db import get_db

with get_db() as conn:
    for filename in os.listdir('reviews'):
        if not filename.endswith('.json'): continue
        with open(os.path.join('reviews', filename), 'r') as f:
            data = json.load(f)
        for rev in data.get('reviews', []):
            rev_id = rev.get('review_id')
            photos = rev.get('author_photos_count')
            if rev_id and photos is not None:
                conn.execute("UPDATE reviews SET author_photos_count = ? WHERE review_id = ?", (photos, rev_id))
    conn.commit()
print("Photos updated!")
