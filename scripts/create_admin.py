import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Promote a user to admin.")
    parser.add_argument("email", help="The email address of the user to promote.")
    args = parser.parse_args()

    # Import inside main to avoid issues if run from wrong directory
    sys.path.append("./backend/app")
    import os
    os.chdir("./backend")
    from app.db.database import SessionLocal
    from app.models.domain import User

    db = SessionLocal()
    user = db.query(User).filter(User.email == args.email).first()
    
    if not user:
        print(f"User with email '{args.email}' not found.")
        sys.exit(1)
        
    user.is_admin = True
    db.commit()
    print(f"Successfully promoted '{args.email}' to admin!")

if __name__ == "__main__":
    main()
