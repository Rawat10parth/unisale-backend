import os
import json
import requests
import mysql.connector
from flask import Flask, request, redirect, session, jsonify, url_for, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import auth, credentials, firestore
from google.cloud import storage
import uuid, tempfile
from werkzeug.utils import secure_filename
import traceback

# Load environment variables
load_dotenv()

app = Flask(__name__)
# Update CORS configuration to handle all routes and methods
CORS(app, resources={
    r"/*": {
        "origins": ["https://unisale-1556d.web.app/", "http://localhost:5173"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})


# Secret key for session management
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# Microsoft OAuth Config
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")
CLOUD_INSTANCE = os.getenv("CLOUD_INSTANCE", "https://login.microsoftonline.com/")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# Microsoft Authority URLs
AUTHORITY = f"{CLOUD_INSTANCE}{TENANT_ID}/v2.0"
TOKEN_URL = f"{AUTHORITY}/token"
AUTH_URL = f"{AUTHORITY}/authorize"

# Microsoft Graph API Endpoint
GRAPH_API_ENDPOINT = os.getenv("GRAPH_API_ENDPOINT", "https://graph.microsoft.com/")

# Allowed university domain
ALLOWED_DOMAIN = "stu.upes.ac.in"

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "tactile-rigging-451008-a0-f0a39bd91c95.json"

# =================== MYSQL CONNECTION SETUP =================== #

# Add Google Cloud SQL Configuration
CLOUD_SQL_CONFIG = {
    'host': '34.131.40.156',  # Your Cloud SQL instance IP
    'user': 'root',           # Your Cloud SQL username
    'password': 'parth@123',  # Your Cloud SQL password
    'database': 'unisale',    # Your database name
}
#my ip 106.215.163.19

# Update the database connection function
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=CLOUD_SQL_CONFIG['host'],
            user=CLOUD_SQL_CONFIG['user'],
            password=CLOUD_SQL_CONFIG['password'],
            database=CLOUD_SQL_CONFIG['database'],
        )
        return connection
    except mysql.connector.Error as err:
        print(f"Error connecting to Cloud SQL: {err}")
        raise


# =================== FIREBASE AUTH SETUP =================== #

cred = credentials.Certificate("firebase-adminsdk.json")  # Update path
firebase_admin.initialize_app(cred)

# After existing Firebase initialization
db = firestore.client()

# Authentication middleware
def authenticate_token(token):
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except Exception as e:
        print(f"Auth error: {e}")
        return None


# Utility function to get Firebase UID from token
def get_current_user_id():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None

    try:
        token = auth_header.split(' ')[1]
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except Exception as e:
        print(f"Error authenticating token: {e}")
        return None


# Get product by ID
def get_product_by_id(product_id):
    cursor = mysql.connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM product WHERE id = %s", (product_id,))
    return cursor.fetchone()


# Delete product by ID
def delete_product_by_id(product_id):
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM product WHERE id = %s", (product_id,))
    mysql.connection.commit()


# =================== ROUTES =================== #

@app.route("/")
def home():
    return "Welcome to UniSale API!"


@app.route("/users", methods=["GET"])
def get_users():
    """Fetch all users from the database (test route)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, email, verified FROM users")
        users = cursor.fetchall()
        conn.close()
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    email = data.get("email")
    name = data.get("name")

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check if user already exists
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            return jsonify({"success": False, "message": "User already exists!"})

        # Insert new user
        cursor.execute("INSERT INTO users (name, email, verified) VALUES (%s, %s, 1)", (name, email))
        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": "Signup successful!"})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# =================== Google Cloud Storage Setup =================== #

BUCKET_NAME = "unisale-storage"


def gcs_upload_image(file, folder):
    """Uploads an image to Google Cloud Storage under the specified folder and returns the public URL."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)

        # Generate a unique filename inside the folder
        unique_filename = f"{folder}/{uuid.uuid4()}_{secure_filename(file.filename)}"
        blob = bucket.blob(unique_filename)

        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            file.save(temp_file.name)
            temp_file_path = temp_file.name

        # Upload the file to GCS
        blob.upload_from_filename(temp_file_path)
        blob.make_public()
        public_url = blob.public_url
        print(f"Image uploaded to {public_url}")

        # Remove the temporary file
        os.unlink(temp_file_path)

        return public_url
    except Exception as e:
        print(f"Error uploading file to GCS: {str(e)}")
        # Ensure temporary file is removed even if an error occurs
        if 'temp_file_path' in locals():
            try:
                os.unlink(temp_file_path)
            except Exception as del_error:
                print(f"Error deleting temporary file: {str(del_error)}")
        return None


def delete_from_gcs(public_url):
    """Deletes an image from Google Cloud Storage using its public URL."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        # Extract blob name from public URL
        blob_name = public_url.split(f'{BUCKET_NAME}/')[1]
        blob = bucket.blob(blob_name)
        blob.delete()
    except Exception as e:
        print(f"Error deleting image from GCS: {str(e)}")


db = mysql.connector.connect(
    host="34.131.40.156", user="root", password="parth@123", database="unisale"
)
cursor = db.cursor()

@app.route("/api/upload", methods=["POST"])
def upload_product():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Your code here
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/update-profile-picture", methods=["POST"])
def update_profile_picture():
    user_id = request.form.get("user_id")
    if "image" not in request.files or not user_id:
        return jsonify({"error": "Missing image or user_id"}), 400

    file = request.files["image"]
    image_url = gcs_upload_image(file, "profile-picture")  # Upload to 'profile-picture' folder
    if not image_url:
        return jsonify({"error": "Image upload failed"}), 500

    try:
        cursor.execute("UPDATE users SET profile_picture = %s WHERE id = %s", (image_url, user_id))
        db.commit()
        return jsonify({"message": "Profile picture updated", "image_url": image_url}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Fetch User Profile API
@app.route('/get-profile', methods=['POST', 'GET'])
def get_profile():
    email = None

    if request.method == 'GET':
        email = request.args.get('email')
    else:
        data = request.json
        email = data.get('email') if data else None

    if not email:
        return jsonify({"error": "Email is required"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, profile_picture, phone FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        conn.close()

        if user:
            return jsonify({
                "id": user["id"],
                "name": user["name"],
                "profilePic": user["profile_picture"] or "https://via.placeholder.com/150",
                "phoneNumber": user["phone"] or ""
            })
        else:
            return jsonify({"error": "User not found"}), 404

    except Exception as e:
        print("Error in get-profile route:")
        print(traceback.format_exc())  # Logs full error stack trace
        return jsonify({"error": str(e)}), 500


@app.route("/update-name", methods=["POST"])
def update_name():
    data = request.json
    user_id = data.get("user_id")
    name = data.get("name")

    if not user_id or not name:
        return jsonify({"error": "Missing user_id or name"}), 400

    try:
        cursor.execute("UPDATE users SET name = %s WHERE id = %s", (name, user_id))
        db.commit()
        return jsonify({"message": "Name updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/update-phone-number", methods=["POST"])
def update_phone_number():
    data = request.json
    user_id = data.get("user_id")
    phone_number = data.get("phone_number")

    # Validate phone number: must be 10 digits
    if not user_id or not phone_number or not phone_number.isdigit() or len(phone_number) != 10:
        return jsonify({"error": "Invalid phone number. Must be exactly 10 digits."}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET phone = %s WHERE id = %s", (phone_number, user_id))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "Phone number updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/get-products", methods=["GET"])
def get_products():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Include id so that products in the frontend have an identifier.
        cursor.execute("SELECT id, user_id, name, description, category, state, price, image_url FROM products")
        products = cursor.fetchall()
        conn.close()
        return jsonify(products)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    # You can add authorization checks here if needed,
    # for example, ensuring the current user is the owner of the product.
    data = request.json
    # Make sure to get the necessary fields from the request.
    name = data.get("name")
    description = data.get("description")
    category = data.get("category")
    state = data.get("state")
    price = data.get("price")

    # Validate that all required fields are provided.
    if not all([name, description, category, state, price]):
        return jsonify({"error": "All fields are required to update the product"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        update_query = """
            UPDATE products
            SET name = %s, description = %s, category = %s, state = %s, price = %s
            WHERE id = %s
        """
        cursor.execute(update_query, (name, description, category, state, price, product_id))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "Product updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/userid')
def get_user_id():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify({'user_id': user_id})


@app.route('/toggle-wishlist', methods=['POST'])
def toggle_wishlist():
    data = request.json
    print(f"Received wishlist toggle request: {data}")  # Add debug logging

    user_id = data.get("users_id")
    image_url = data.get("image_url")

    if not user_id or not image_url:
        print(f"Missing fields - user_id: {user_id}, image_url: {image_url}")
        return jsonify({"error": "Missing fields"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check if item exists
        cursor.execute(
            "SELECT * FROM wishlist WHERE users_id = %s AND image_url = %s",
            (user_id, image_url)
        )
        existing = cursor.fetchone()
        print(f"Existing wishlist item: {existing}")  # Add debug logging

        if existing:
            cursor.execute(
                "DELETE FROM wishlist WHERE users_id = %s AND image_url = %s",
                (user_id, image_url)
            )
            result = {"message": "Removed from wishlist", "status": "removed"}
        else:
            cursor.execute(
                "INSERT INTO wishlist (users_id, image_url) VALUES (%s, %s)",
                (user_id, image_url)
            )
            result = {"message": "Added to wishlist", "status": "added"}

        conn.commit()
        cursor.close()
        conn.close()
        print(f"Operation result: {result}")  # Add debug logging
        return jsonify(result), 200

    except Exception as e:
        print(f"Error in toggle-wishlist: {str(e)}")
        traceback.print_exc()  # Add full traceback
        return jsonify({"error": str(e)}), 500


@app.route('/get-wishlist', methods=['GET'])
def get_wishlist():
    user_id = request.args.get('user_id')
    print(f"Received request for user_id: {user_id}")  # Add debug logging

    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT image_url FROM wishlist WHERE users_id = %s",
            (user_id,)
        )
        wishlist_items = cursor.fetchall()
        print(f"Found wishlist items: {wishlist_items}")  # Add debug logging

        # If the wishlist is empty, clean up and return an empty list
        if not wishlist_items:
            cursor.close()
            conn.close()
            return jsonify([])

        image_urls = [item[0] for item in wishlist_items]
        print(f"Image URLs: {image_urls}")  # Add debug logging

        # Use dictionary cursor for better data handling
        cursor = conn.cursor(dictionary=True)
        placeholders = ', '.join(['%s'] * len(image_urls))
        
        query = f"""
            SELECT id, name, description, price, state, category, image_url, user_id 
            FROM products 
            WHERE image_url IN ({placeholders})
        """
        cursor.execute(query, tuple(image_urls))
        products = cursor.fetchall()
        print(f"Found products: {products}")  # Add debug logging

        cursor.close()
        conn.close()
        return jsonify(products)  # Return products directly since we're using dictionary cursor

    except Exception as e:
        print(f"Error in get-wishlist: {str(e)}")
        traceback.print_exc()  # Add full traceback
        return jsonify({"error": str(e)}), 500


@app.route('/product/<int:product_id>', methods=['GET'])
def get_product_detail(product_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get product details
        cursor.execute("""
            SELECT p.id, p.user_id, p.name, p.description, p.category, p.state, 
                   p.price, p.image_url as main_image, p.created_at,
                   GROUP_CONCAT(pi.image_url) as additional_images
            FROM products p
            LEFT JOIN product_images pi ON p.id = pi.product_id
            WHERE p.id = %s
            GROUP BY p.id
        """, (product_id,))
        product = cursor.fetchone()

        if not product:
            return jsonify({"error": "Product not found"}), 404

        # Get seller details
        cursor.execute("""
            SELECT id, name, email, profile_picture as profilePic, phone as phoneNumber
            FROM users
            WHERE id = %s
        """, (product.get('user_id'),))
        seller = cursor.fetchone()

        # Process the additional images
        all_images = [product['main_image']]  # Start with main image
        if product['additional_images']:
            additional_images = product['additional_images'].split(',')
            all_images.extend(additional_images)

        # Format the product data
        formatted_product = {
            **product,
            'images': all_images,  # Add all images array
            'created_at': product['created_at'].isoformat() if product['created_at'] else None
        }
        del formatted_product['additional_images']  # Remove the concatenated string

        conn.close()

        return jsonify({
            "product": formatted_product,
            "seller": seller
        })

    except Exception as e:
        print("Error fetching product details:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/user/<int:user_id>", methods=["GET"])
def get_user_by_id(users_id):
    """Fetch user information by ID."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, email, phone, profile_picture FROM users WHERE id = %s",
            (users_id,)
        )
        users = cursor.fetchone()
        cursor.close()
        conn.close()

        if not users:
            return jsonify({"error": "User not found"}), 404

        # Don't expose sensitive information
        return jsonify({
            "id": users["id"],
            "name": users["name"],
            "email": users["email"],
            "phone": users["phone"],
            "profilePic": users["profile_picture"]
        })
    except Exception as e:
        print(f"Error fetching user: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload-multiple", methods=["POST"])
def upload_multiple_images():
    if 'images[]' not in request.files:
        return jsonify({"error": "No images uploaded"}), 400

    files = request.files.getlist('images[]')
    if not files or len(files) == 0:
        return jsonify({"error": "No valid images found"}), 400

    uploaded_urls = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Upload all images first
        for file in files:
            image_url = gcs_upload_image(file, "product-image")
            if not image_url:
                # If any upload fails, delete previously uploaded images
                for url in uploaded_urls:
                    delete_from_gcs(url)  # You'll need to implement this function
                return jsonify({"error": "Image upload failed"}), 500
            uploaded_urls.append(image_url)

        # Get product details from form data
        user_id = request.form.get("user_id")
        name = request.form.get("name")
        description = request.form.get("description")
        category = request.form.get("category")
        state = request.form.get("state")
        price = request.form.get("price")

        if not all([user_id, name, description, category, state, price]):
            # Delete all uploaded images if validation fails
            for url in uploaded_urls:
                delete_from_gcs(url)
            return jsonify({"error": "All fields are required"}), 400

        # Insert the main product with first image
        cursor.execute(
            "INSERT INTO products (user_id, name, description, category, state, price, image_url) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, name, description, category, state, price, uploaded_urls[0])
        )
        product_id = cursor.lastrowid

        # Insert additional images
        if len(uploaded_urls) > 1:
            for url in uploaded_urls[1:]:
                cursor.execute(
                    "INSERT INTO product_images (product_id, image_url) VALUES (%s, %s)",
                    (product_id, url)
                )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "message": "Product uploaded successfully",
            "product_id": product_id,
            "images": uploaded_urls
        }), 201

    except Exception as e:
        # Delete all uploaded images if there's an error
        for url in uploaded_urls:
            delete_from_gcs(url)
        return jsonify({"error": str(e)}), 500
    

# Cart Routes
@app.route('/api/cart', methods=['GET'])
def get_cart():
    try:
        user_id = get_current_user_id()
        print(f"User ID from token: {user_id}")  # Debug log
        
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT c.id as cart_id, c.quantity, 
                   p.id as product_id, p.name, p.description, p.price, p.image_url,
                   u.name as seller_name
            FROM cart c
            JOIN products p ON c.product_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE c.user_id = %s
        """, (user_id,))
        
        cart_items = cursor.fetchall()
        print(f"Found cart items: {cart_items}")  # Debug log
        
        conn.close()
        return jsonify(cart_items)
        
    except Exception as e:
        print(f"Error fetching cart: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/cart/<int:user_id>', methods=['GET'])
def get_cart_items(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT c.*, p.name, p.price, p.image_url, p.description 
            FROM cart c 
            JOIN products p ON c.product_id = p.id 
            WHERE c.user_id = %s
        """, (user_id,))
        
        cart_items = cursor.fetchall()
        conn.close()
        
        return jsonify(cart_items)
    except Exception as e:
        print(f"Error fetching cart items: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    user_id = int(data.get('userId'))  # Convert to int
    product_id = int(data.get('productId'))  # Convert to int
    quantity = int(data.get('quantity', 1))  # Convert to int
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if item exists in cart
        cursor.execute(
            "SELECT * FROM cart WHERE user_id = %s AND product_id = %s",
            (user_id, product_id)
        )
        existing_item = cursor.fetchone()
        
        if existing_item:
            cursor.execute(
                "UPDATE cart SET quantity = quantity + %s WHERE user_id = %s AND product_id = %s",
                (quantity, user_id, product_id)
            )
        else:
            cursor.execute(
                "INSERT INTO cart (user_id, product_id, quantity) VALUES (%s, %s, %s)",
                (user_id, product_id, quantity)
            )
            
        conn.commit()
        conn.close()
        return jsonify({"message": "Added to cart successfully"})
        
    except Exception as e:
        print(f"Error adding to cart: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/cart/remove', methods=['POST'])
def remove_from_cart():
    try:
        data = request.json
        user_id = data.get('userId')
        product_id = data.get('productId')

        if not user_id or not product_id:
            return jsonify({"error": "User ID and Product ID are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # First check if the item exists in the cart
        cursor.execute(
            "SELECT * FROM cart WHERE user_id = %s AND product_id = %s",
            (user_id, product_id)
        )
        if not cursor.fetchone():
            conn.close()
            return jsonify({"error": "Item not found in cart"}), 404

        # Delete the item from cart
        cursor.execute(
            "DELETE FROM cart WHERE user_id = %s AND product_id = %s",
            (user_id, product_id)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "Item removed successfully"})

    except Exception as e:
        print(f"Error removing item from cart: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/wishlist/check/<product_id>', methods=['POST'])
def check_wishlist_status(product_id):
    data = request.get_json()
    user_id = data.get('userId')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM wishlist WHERE users_id = %s AND product_id = %s",
            (user_id, product_id)
        )
        wishlist_item = cursor.fetchone()

        conn.close()

        if wishlist_item:
            return jsonify({"status": "exists"})
        else:
            return jsonify({"status": "not_exists"})
    except Exception as e:
        print(f"Error checking wishlist status: {str(e)}")
        return jsonify({"error": str(e)}), 500


# Checkout Routes
@app.route('/api/checkout', methods=['POST'])
def create_order():
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            # Start transaction - Changed from begin() to start_transaction()
            conn.start_transaction()

            # Get cart items first
            cursor.execute("""
                SELECT c.product_id, c.quantity, p.price, p.name
                FROM cart c
                JOIN products p ON c.product_id = p.id
                WHERE c.user_id = %s
            """, (user_id,))
            
            cart_items = cursor.fetchall()
            if not cart_items:
                return jsonify({"error": "Cart is empty"}), 400

            # Calculate total amount
            total_amount = sum(item['price'] * item['quantity'] for item in cart_items)

            # Create order
            cursor.execute("""
                INSERT INTO orders (user_id, total_amount, status) 
                VALUES (%s, %s, 'pending')
            """, (user_id, total_amount))
            
            order_id = cursor.lastrowid

            # Create delivery address
            cursor.execute("""
                INSERT INTO delivery_addresses 
                (order_id, user_id, full_name, phone, address, city, state, pincode, hostel_room)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                order_id,
                user_id,
                data['fullName'],
                data['phone'],
                data['address'],
                data['city'],
                data['state'],
                data['pincode'],
                data.get('hostelRoom', '')
            ))

            # Create order items
            for item in cart_items:
                cursor.execute("""
                    INSERT INTO order_items (order_id, product_id, quantity, price)
                    VALUES (%s, %s, %s, %s)
                """, (order_id, item['product_id'], item['quantity'], item['price']))

            # Clear cart
            cursor.execute("DELETE FROM cart WHERE user_id = %s", (user_id,))

            # Commit transaction
            conn.commit()

            print(f"Order created successfully: {order_id}")
            return jsonify({
                "message": "Order placed successfully",
                "orderId": order_id
            })

        except Exception as e:
            conn.rollback()
            print(f"Error in transaction: {str(e)}")
            raise e

        finally:
            conn.close()

    except Exception as e:
        print(f"Error creating order: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/orders', methods=['GET'])
def get_orders():
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Updated query with correct JOIN condition
        cursor.execute("""
            SELECT 
                o.id, o.user_id, o.total_amount, o.status, o.created_at,
                da.full_name, da.phone, da.address, da.city, da.state, da.pincode,
                GROUP_CONCAT(oi.product_id) as product_ids,
                GROUP_CONCAT(oi.quantity) as quantities,
                GROUP_CONCAT(oi.price) as prices,
                GROUP_CONCAT(p.name) as product_names,
                GROUP_CONCAT(p.image_url) as image_urls
            FROM orders o
            LEFT JOIN delivery_addresses da ON o.id = da.order_id
            LEFT JOIN order_items oi ON o.id = oi.order_id
            LEFT JOIN products p ON oi.product_id = p.id
            WHERE o.user_id = %s
            GROUP BY o.id, da.id
            ORDER BY o.created_at DESC
        """, (user_id,))
        
        orders_data = cursor.fetchall()
        print(f"Orders data: {orders_data}")  # Debug log
        
        orders = []
        for order in orders_data:
            # Format items data
            product_ids = str(order['product_ids']).split(',') if order['product_ids'] else []
            quantities = str(order['quantities']).split(',') if order['quantities'] else []
            prices = str(order['prices']).split(',') if order['prices'] else []
            names = str(order['product_names']).split(',') if order['product_names'] else []
            images = str(order['image_urls']).split(',') if order['image_urls'] else []
            
            items = [
                {
                    'id': pid,
                    'quantity': int(qty),
                    'price': float(price),
                    'name': name,
                    'image_url': img
                }
                for pid, qty, price, name, img in zip(product_ids, quantities, prices, names, images)
                if pid and qty and price and name
            ]
            
            orders.append({
                'id': order['id'],
                'total_amount': float(order['total_amount']),
                'status': order['status'],
                'created_at': order['created_at'].isoformat() if order['created_at'] else None,
                'delivery_address': {
                    'full_name': order['full_name'],
                    'phone': order['phone'],
                    'address': order['address'],
                    'city': order['city'],
                    'state': order['state'],
                    'pincode': order['pincode']
                },
                'items': items
            })
        
        print(f"Formatted orders: {orders}")  # Debug log
        return jsonify(orders)
        
    except Exception as e:
        print(f"Error fetching orders: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/orders/<order_id>', methods=['GET'])
def get_order_details(order_id):
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get order details
        cursor.execute("""
            SELECT o.*, 
                   da.full_name, da.phone, da.address, da.city, da.state, 
                   da.pincode, da.hostel_room
            FROM orders o
            LEFT JOIN delivery_addresses da ON da.user_id = o.user_id  # Changed JOIN condition
            WHERE o.id = %s AND o.user_id = %s
        """, (order_id, user_id))
        
        order = cursor.fetchone()
        
        if not order:
            return jsonify({"error": "Order not found"}), 404
            
        # Get order items
        cursor.execute("""
            SELECT oi.*, p.name, p.image_url
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (order_id,))
        
        items = cursor.fetchall()
        
        # Format the response with proper date handling
        order['created_at'] = order['created_at'].isoformat() if order['created_at'] else None
        order['updated_at'] = order['updated_at'].isoformat() if order['updated_at'] else None
        
        response = {
            'id': order['id'],
            'status': order['status'],
            'total_amount': float(order['total_amount']),
            'created_at': order['created_at'],
            'updated_at': order['updated_at'],
            'delivery_address': {
                'full_name': order['full_name'],
                'phone': order['phone'],
                'address': order['address'],
                'city': order['city'],
                'state': order['state'],
                'pincode': order['pincode'],
                'hostel_room': order['hostel_room']
            },
            'items': [{
                'id': item['id'],
                'name': item['name'],
                'quantity': item['quantity'],
                'price': float(item['price']),
                'image_url': item['image_url']
            } for item in items]
        }
        
        conn.close()
        return jsonify(response)
        
    except Exception as e:
        print(f"Error fetching order details: {str(e)}")


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))  # Use PORT env variable or default to 8080
    app.run(host="0.0.0.0", port=port)

# curl -X POST -F "image=@Zoro-Wallpaper-4k.jpg" http://127.0.0.1:5000/upload-image