from flask import Flask, render_template, request, jsonify
import sqlite3
import pandas as pd
import os

app = Flask(__name__)

# データベースの初期化
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 生徒テーブル
    c.execute('''CREATE TABLE IF NOT EXISTS students
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  student_id TEXT UNIQUE NOT NULL,
                  gender TEXT NOT NULL)''')
    
    # 学級テーブル（display_orderカラムを追加）
    c.execute('''CREATE TABLE IF NOT EXISTS classes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  display_order INTEGER DEFAULT 0)''')
    
    # 生徒と学級の関連テーブル
    c.execute('''CREATE TABLE IF NOT EXISTS student_classes
                 (student_id INTEGER,
                  class_id INTEGER,
                  FOREIGN KEY (student_id) REFERENCES students (id),
                  FOREIGN KEY (class_id) REFERENCES classes (id),
                  PRIMARY KEY (student_id, class_id))''')
    
    conn.commit()
    conn.close()

# アプリケーション起動時にデータベースを初期化
init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/students', methods=['GET'])
def get_students():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT id, name, student_id, gender FROM students')
    students = [{'id': row[0], 'name': row[1], 'student_id': row[2], 'gender': row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify(students)

@app.route('/classes', methods=['GET'])
def get_classes():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 学級とその生徒を取得（display_orderでソート）
    c.execute('''
        SELECT c.id, c.name, s.id, s.name, s.student_id, s.gender
        FROM classes c
        LEFT JOIN student_classes sc ON c.id = sc.class_id
        LEFT JOIN students s ON sc.student_id = s.id
        ORDER BY c.display_order
    ''')
    
    # 結果を整理
    classes = {}
    for row in c.fetchall():
        class_id, class_name, student_id, student_name, student_number, gender = row
        if class_id not in classes:
            classes[class_id] = {
                'id': class_id,
                'name': class_name,
                'students': []
            }
        if student_id:  # 生徒がいる場合のみ追加
            classes[class_id]['students'].append({
                'id': student_id,
                'name': student_name,
                'student_id': student_number,
                'gender': gender
            })
    
    conn.close()
    return jsonify(list(classes.values()))

@app.route('/classes', methods=['POST'])
def add_class():
    data = request.get_json()
    class_name = data.get('name')
    
    if not class_name:
        return jsonify({'error': '学級名が必要です'}), 400
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('INSERT INTO classes (name) VALUES (?)', (class_name,))
    class_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        'id': class_id,
        'name': class_name,
        'students': []
    })

@app.route('/move-student', methods=['POST'])
def move_student():
    data = request.get_json()
    student_id = data.get('student_id')
    class_id = data.get('class_id')
    
    if not student_id or not class_id:
        return jsonify({'error': '生徒IDと学級IDが必要です'}), 400
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 生徒が既に他の学級に所属している場合は削除
    c.execute('DELETE FROM student_classes WHERE student_id = ?', (student_id,))
    
    # 新しい学級に生徒を追加
    c.execute('INSERT INTO student_classes (student_id, class_id) VALUES (?, ?)',
              (student_id, class_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': '生徒を移動しました'})

@app.route('/remove-student', methods=['POST'])
def remove_student():
    data = request.get_json()
    student_id = data.get('student_id')
    class_id = data.get('class_id')
    
    if not student_id or not class_id:
        return jsonify({'error': '生徒IDと学級IDが必要です'}), 400
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 生徒を学級から削除
    c.execute('DELETE FROM student_classes WHERE student_id = ? AND class_id = ?',
              (student_id, class_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': '生徒を学級から削除しました'})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルがありません'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400
    
    if file and file.filename.endswith('.csv'):
        try:
            # CSVファイルを読み込む
            df = pd.read_csv(file)
            
            # 必要なカラムの確認
            required_columns = ['name', 'student_id', 'gender']
            if not all(col in df.columns for col in required_columns):
                return jsonify({'error': 'CSVファイルには name, student_id, gender のカラムが必要です'}), 400
            
            # 性別の値を正規化（M/F → 男/女）
            df['gender'] = df['gender'].map({
                'M': '男',
                'F': '女',
                'm': '男',
                'f': '女'
            }).fillna(df['gender'])
            
            # 有効な性別値の確認
            valid_genders = ['男', '女']
            invalid_rows = df[~df['gender'].isin(valid_genders)]
            if not invalid_rows.empty:
                return jsonify({'error': f'無効な性別値があります: {", ".join(invalid_rows["gender"].unique())}'}), 400
            
            # SQLiteデータベースに接続
            conn = sqlite3.connect('database.db')
            
            # データフレームをSQLiteに書き込む
            df.to_sql('students', conn, if_exists='append', index=False)
            
            conn.close()
            return jsonify({'message': '生徒データのインポートに成功しました'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({'error': 'CSVファイルのみアップロード可能です'}), 400

@app.route('/reset', methods=['POST'])
def reset_data():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 関連テーブルから削除（外部キー制約があるため）
    c.execute('DELETE FROM student_classes')
    
    # 生徒テーブルから削除
    c.execute('DELETE FROM students')
    
    # 学級テーブルから削除
    c.execute('DELETE FROM classes')
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'すべてのデータを初期化しました'})

@app.route('/update-class-order', methods=['POST'])
def update_class_order():
    data = request.get_json()
    new_order = data.get('order')
    
    if not new_order:
        return jsonify({'error': '順序データが必要です'}), 400
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        # 学級の順序を更新
        for index, class_id in enumerate(new_order):
            c.execute('UPDATE classes SET display_order = ? WHERE id = ?', (index, class_id))
        
        conn.commit()
        return jsonify({'message': '学級の順序を更新しました'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True) 