from flask import Flask, send_from_directory,render_template, request, redirect, url_for, session, flash, jsonify, send_file
from datetime import datetime
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from inference import detect_image
import tempfile

app = Flask(__name__)
app.secret_key = 'my_secret_key'  

# 数据库初始化
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 创建用户表
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            name TEXT,
            age INTEGER,
            occupation TEXT,
            bio TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建海洋生物表
    c.execute('''
        CREATE TABLE IF NOT EXISTS marine_life (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            scientific_name TEXT,
            description TEXT,
            habitat TEXT,
            image_url TEXT,
            category TEXT DEFAULT 'normal',  -- normal/endangered
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    #创建历史识别图片存储表
    c.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            local_path TEXT NOT NULL,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # 创建反馈表
    c.execute('''
        CREATE TABLE IF NOT EXISTS feedbacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT DEFAULT 'pending',  -- pending, reviewed, resolved
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # 添加示例用户
    try:
        hashed_password = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, password, role, name) VALUES (?, ?, ?, ?)", 
                 ('admin', hashed_password, 'admin', '管理员'))
        
        hashed_password = generate_password_hash('user123')
        c.execute("INSERT INTO users (username, password, name) VALUES (?, ?, ?)", 
                 ('user1', hashed_password, '普通用户'))
    except sqlite3.IntegrityError:
        pass  # 用户已存在
    
    # 添加示例海洋生物
    try:
        c.execute("INSERT INTO marine_life (name, scientific_name, description, habitat, category, image_url) VALUES (?, ?, ?, ?, ?, ?)",
                 ('小丑鱼', 'Amphiprioninae', '小丑鱼是对雀鲷科海葵鱼亚科鱼类的俗称，因为脸上都有一条或两条白色条纹，好似京剧中的丑角而得名。', '热带珊瑚礁海域', 'normal', '/static/images/clownfish.jpg'))
        
        c.execute("INSERT INTO marine_life (name, scientific_name, description, habitat, category, image_url) VALUES (?, ?, ?, ?, ?, ?)",
                 ('蓝鲸', 'Balaenoptera musculus', '蓝鲸是地球上现存体型最大的动物，长可达33米，重达181吨。', '全球各大洋', 'endangered', '/static/images/Blue whale.jpg'))
        
        c.execute("INSERT INTO marine_life (name, scientific_name, description, habitat, category, image_url) VALUES (?, ?, ?, ?, ?, ?)",
                 ('玳瑁', 'Eretmochelys imbricata', '玳瑁是海龟科的一种，背甲呈覆瓦状排列，色泽美丽，被列为极危物种。', '热带和亚热带海域', 'endangered', 'static/images/hawksbill.jpg'))
        
        c.execute("INSERT INTO marine_life (name, scientific_name, description, habitat, category, image_url) VALUES (?, ?, ?, ?, ?, ?)",
                 ('海马', 'Hippocampus', '海马是一种小型海洋鱼类，因其头部像马而得名，是海洋中唯一雄性生育的动物。', '浅海海域', 'normal', 'static/images/Seahorse.jpg'))
    except sqlite3.IntegrityError:
        pass
    
    conn.commit()
    conn.close()

# 初始化数据库
init_db()

# 获取用户信息
def get_user_info(username):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    
    if user:
        return {
            'id': user[0],
            'username': user[1],
            'name': user[4],
            'age': user[5],
            'nationality': user[6],
            'occupation': user[7],
            'bio': user[8]
        }
    return None

# 更新用户信息
def update_user_info(username, name, age, nationality, occupation, bio):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        UPDATE users SET 
            name = ?,
            age = ?,
            nationality = ?,
            occupation = ?,
            bio = ?
        WHERE username = ?
    ''', (name, age, nationality, occupation, bio, username))
    conn.commit()
    conn.close()

# 插入图片信息到数据库
def insert_image_info(filename, local_path, user_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO images (filename, local_path, user_id) VALUES (?, ?, ?)", 
                 (filename, local_path, user_id))
        conn.commit()
    except Exception as e:
        print(f"Error inserting image info: {e}")
        conn.rollback()
    finally:
        conn.close()

# 提交反馈
def submit_feedback(user_id, username, content):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO feedbacks (user_id, username, content) VALUES (?, ?, ?)", 
             (user_id, username, content))
    conn.commit()
    conn.close()

# 获取用户反馈
def get_user_feedbacks(username):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM feedbacks WHERE username = ? ORDER BY created_at DESC", (username,))
    feedbacks = c.fetchall()
    conn.close()
    
    feedback_list = []
    for fb in feedbacks:
        feedback_list.append({
            'id': fb[0],
            'user_id': fb[1],
            'username': fb[2],
            'content': fb[3],
            'status': fb[4],
            'created_at': fb[5]
        })
    return feedback_list

# 管理员获取反馈
def get_all_feedbacks():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM feedbacks ORDER BY created_at DESC")
    feedbacks = c.fetchall()
    conn.close()
    
    feedback_list = []
    for fb in feedbacks:
        feedback_list.append({
            'id': fb[0],
            'user_id': fb[1],
            'username': fb[2],
            'content': fb[3],
            'status': fb[4],
            'created_at': fb[5]
        })
    return feedback_list

# 获取所有海洋生物
def get_all_marine_life():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM marine_life")
    marine_life = c.fetchall()
    conn.close()
    
    marine_life_list = []
    for life in marine_life:
        marine_life_list.append({
            'id': life[0],
            'name': life[1],
            'scientific_name': life[2],
            'description': life[3],
            'habitat': life[4],
            'image_url': life[5],
            'category': life[6],
            'created_at': life[7]
        })
    return marine_life_list

# 添加海洋生物
def add_marine_life(name, scientific_name, description, habitat, image_url, category):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO marine_life (name, scientific_name, description, habitat, image_url, category) VALUES (?, ?, ?, ?, ?, ?)",
             (name, scientific_name, description, habitat, image_url, category))
    conn.commit()
    conn.close()

# 更新海洋生物
def update_marine_life(id, name, scientific_name, description, habitat, image_url, category):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        UPDATE marine_life SET 
            name = ?,
            scientific_name = ?,
            description = ?,
            habitat = ?,
            image_url = ?,
            category = ?
        WHERE id = ?
    ''', (name, scientific_name, description, habitat, image_url, category, id))
    conn.commit()
    conn.close()

# 删除海洋生物
def delete_marine_life(id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM marine_life WHERE id = ?", (id,))
    conn.commit()
    conn.close()

# 登录路由
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'user')
        remember = request.form.get('remember')
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT id, username, password, role FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            # 检查用户角色是否匹配
            if user[3] != role:
                flash('登录失败：用户角色不匹配', 'error')
                return redirect(url_for('login'))
                
            # 登录成功，设置会话
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]
            
            # 记住密码功能
            if remember:
                session.permanent = True
            else:
                session.permanent = False
            
            # 跳转到主页面
            return redirect(url_for('home'))
        else:
            flash('登录失败，请检查账号和密码', 'error')
    
    return render_template('login.html')

# 注册路由
@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    
    # 验证输入
    if not username or not password:
        flash('用户名和密码不能为空', 'error')
        return redirect(url_for('index'))
    
    if password != confirm_password:
        flash('两次输入的密码不一致', 'error')
        return redirect(url_for('index'))
    
    if len(password) < 6:
        flash('密码长度至少为6个字符', 'error')
        return redirect(url_for('index'))
    
    # 哈希密码
    hashed_password = generate_password_hash(password)
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                 (username, hashed_password))
        conn.commit()
        flash('注册成功！请登录', 'success')
    except sqlite3.IntegrityError:
        flash('用户名已被使用', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('index'))

# 主页路由
@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    user_info = get_user_info(session['username'])
    current_date = datetime.now().strftime("%Y年%m月%d日")
    
    return render_template('home.html', 
                          user_info=user_info, 
                          current_date=current_date)

# 更新个人信息
@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    name = request.form.get('name')
    age = request.form.get('age')
    nationality = request.form.get('nationality')
    occupation = request.form.get('occupation')
    bio = request.form.get('bio')
    
    # 更新用户信息
    update_user_info(
        session['username'],
        name,
        int(age) if age else None,
        nationality,
        occupation,
        bio
    )
    
    flash('个人信息已更新', 'success')
    return redirect(url_for('home'))

# 提交反馈API
@app.route('/submit_feedback', methods=['POST'])
def api_submit_feedback():
    if 'username' not in session:
        return jsonify({'success': False, 'message': '用户未登录'}), 401
    
    data = request.get_json()
    content = data.get('content')
    
    if not content:
        return jsonify({'success': False, 'message': '反馈内容不能为空'}), 400
    
    # 提交反馈
    submit_feedback(session['user_id'], session['username'], content)
    
    return jsonify({
        'success': True,
        'message': '反馈提交成功'
    })

# 获取用户反馈API
@app.route('/get_feedbacks', methods=['GET'])
def api_get_feedbacks():
    if 'username' not in session:
        return jsonify({'success': False, 'message': '用户未登录'}), 401
    
    username = session['username']
    feedbacks = get_user_feedbacks(username)
    
    return jsonify({
        'success': True,
        'feedbacks': feedbacks
    })

# 管理员获取反馈API
@app.route('/admin/feedbacks', methods=['GET'])
def api_admin_feedbacks():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403

    status_filter = request.args.get('status', 'all')
    username_filter = request.args.get('username', '')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    query = "SELECT * FROM feedbacks"
    conditions = []
    values = []

    if status_filter != 'all':
        conditions.append("status = ?")
        values.append(status_filter)

    if username_filter:
        conditions.append("username = ?")
        values.append(username_filter)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC"

    c.execute(query, values)
    feedbacks = c.fetchall()
    conn.close()

    feedback_list = []
    for fb in feedbacks:
        feedback_list.append({
            'id': fb[0],
            'user_id': fb[1],
            'username': fb[2],
            'content': fb[3],
            'status': fb[4],
            'created_at': fb[5]
        })

    return jsonify({
        'success': True,
        'feedbacks': feedback_list
    })


# 退出登录
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/detect', methods=['POST'])
def detect():
    if 'username' not in session or session['role'] != 'user':
        return redirect('/')
    if 'file' not in request.files:
        return jsonify({'error': 'no file'}), 400
    f = request.files['file']
    img_bytes = f.read()
    result, vis, dt = detect_image(img_bytes)
    save_dir = 'detected_images'
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    # 生成唯一的文件名
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{session['username']}_{timestamp}.jpg"
    save_path = os.path.join(save_dir, filename)
    # 保存图片到本地目录
    with open(save_path, 'wb') as img_file:
        img_file.write(vis)
    # 将可视化结果写入临时文件返回
    user_id = session.get('user_id')
    insert_image_info(filename, save_path, user_id)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
    tmp.write(vis)

    tmp.close()
   
    return jsonify({'time': round(dt * 1000, 1),
                    'detections': result,
                    'vis_path': '/result/' + os.path.basename(tmp.name)})

@app.route('/result/<name>')
def result_img(name):
    try:
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, name)
        return send_file(file_path, mimetype='image/jpeg')
    except FileNotFoundError:
        return jsonify({'error': 'Image file not found'}), 404
    
@app.route('/user_detected_images')
def user_detected_images():
    if 'username' not in session:
        return redirect(url_for('index'))
    user_id = session.get('user_id')
    date = request.args.get('date')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if date:
        c.execute("SELECT filename, local_path, upload_time FROM images WHERE user_id = ? AND DATE(upload_time) = ?", (user_id, date))
    else:
        c.execute("SELECT filename, local_path, upload_time FROM images WHERE user_id = ?", (user_id,))
    images = c.fetchall()
    conn.close()
    image_list = []
    for filename, local_path ,upload_time in images:
        vis_path = '/detected_images/' + os.path.basename(local_path)
        image_list.append({
            'filename': filename,
            'vis_path': vis_path,
            'created_at': upload_time
        })
    print("image_list 的内容：", image_list)
    return jsonify({'images': image_list})

@app.route('/detected_images/<path:filename>')
def detected_images(filename):
    save_dir = 'detected_images'
    return send_from_directory(save_dir, filename)
    
# 管理员更新反馈状态
@app.route('/admin/update_feedback_status/<int:feedback_id>', methods=['POST'])
def update_feedback_status(feedback_id):
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.get_json()
    new_status = data.get('status')
    
    if new_status not in ['pending', 'reviewed', 'resolved']:
        return jsonify({'success': False, 'message': '无效的状态值'}), 400
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("UPDATE feedbacks SET status = ? WHERE id = ?", (new_status, feedback_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': '反馈状态更新成功'})

# 管理员删除反馈
@app.route('/admin/delete_feedback/<int:feedback_id>', methods=['DELETE'])
def delete_feedback(feedback_id):
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM feedbacks WHERE id = ?", (feedback_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': '反馈删除成功'})
    
# 获取海洋生物API
@app.route('/marine_life', methods=['GET'])
def get_marine_life():
    marine_life = get_all_marine_life()
    return jsonify({
        'success': True,
        'marine_life': marine_life
    })

# 管理员添加海洋生物API
@app.route('/admin/add_marine_life', methods=['POST'])
def api_add_marine_life():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.get_json()
    name = data.get('name')
    scientific_name = data.get('scientific_name')
    description = data.get('description')
    habitat = data.get('habitat')
    image_url = data.get('image_url')
    category = data.get('category', 'normal')
    
    if not name:
        return jsonify({'success': False, 'message': '名称不能为空'}), 400
    
    add_marine_life(name, scientific_name, description, habitat, image_url, category)
    
    return jsonify({
        'success': True,
        'message': '海洋生物添加成功'
    })

# 管理员更新海洋生物API
@app.route('/admin/update_marine_life/<int:id>', methods=['POST'])
def api_update_marine_life(id):
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    data = request.get_json()
    name = data.get('name')
    scientific_name = data.get('scientific_name')
    description = data.get('description')
    habitat = data.get('habitat')
    image_url = data.get('image_url')
    category = data.get('category')
    
    if not name:
        return jsonify({'success': False, 'message': '名称不能为空'}), 400
    
    update_marine_life(id, name, scientific_name, description, habitat, image_url, category)
    
    return jsonify({
        'success': True,
        'message': '海洋生物更新成功'
    })

# 管理员删除海洋生物API
@app.route('/admin/delete_marine_life/<int:id>', methods=['DELETE'])
def api_delete_marine_life(id):
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403
    
    delete_marine_life(id)
    
    return jsonify({
        'success': True,
        'message': '海洋生物删除成功'
    })

if __name__ == '__main__':

    app.run(debug=True)