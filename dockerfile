# ベースイメージ
FROM python:3.11-slim

# 作業ディレクトリ
WORKDIR /app

# 必要ファイルコピー
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 残りのコードコピー
COPY . .

# 環境変数を使用する場合の指定（任意）
ENV PYTHONUNBUFFERED=1

# 実行コマンド
CMD ["python", "bot.py"]
