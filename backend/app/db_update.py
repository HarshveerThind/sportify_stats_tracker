from sqlalchemy import String, Column, Table, create_engine, MetaData, ForeignKey, Boolean, Integer, Float, Date, DateTime, Text, func, insert
import os
from flask import Flask, redirect, request, jsonify, session
from models import db, user_info
import backend.app.app as app

db = create_engine(os.getenv("sqlite:///stats.db"))
metadata = MetaData()
UID = db.execute 
with db.connect() as conn:
    rt = conn.execute(
        select(user_info.c.refresh_token )
    )
