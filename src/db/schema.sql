CREATE EXTENSION IF NOT EXISTS vector;


-- =========================================
-- USER
-- =========================================

CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =========================================
-- ARTICLE
-- =========================================

CREATE TABLE articles (
    id BIGSERIAL PRIMARY KEY,

    title TEXT NOT NULL,
    description TEXT,
    content TEXT,

    category VARCHAR(100),

    url TEXT NOT NULL UNIQUE,

    published_at TIMESTAMP,
    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =========================================
-- ARTICLE EMBEDDING
-- =========================================

CREATE TABLE article_embeddings (
    id BIGSERIAL PRIMARY KEY,

    article_id BIGINT NOT NULL UNIQUE,

    embedding VECTOR(384) NOT NULL,

    model_name VARCHAR(200) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_article_embedding
        FOREIGN KEY (article_id)
        REFERENCES articles(id)
        ON DELETE CASCADE
);


-- =========================================
-- USER PREFERENCE
-- =========================================

CREATE TABLE user_preferences (
    id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL,

    topic VARCHAR(200) NOT NULL,

    weight FLOAT DEFAULT 1.0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_user_preference
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT unique_user_topic
        UNIQUE (user_id, topic)
);


-- =========================================
-- SUMMARY
-- =========================================

CREATE TABLE summaries (
    id BIGSERIAL PRIMARY KEY,

    topic VARCHAR(200) NOT NULL,

    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    summary TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =========================================
-- SUMMARY ARTICLE
-- =========================================

CREATE TABLE summary_articles (
    summary_id BIGINT NOT NULL,
    article_id BIGINT NOT NULL,

    hybrid_score FLOAT,

    PRIMARY KEY (summary_id, article_id),

    CONSTRAINT fk_summary
        FOREIGN KEY (summary_id)
        REFERENCES summaries(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_summary_article
        FOREIGN KEY (article_id)
        REFERENCES articles(id)
        ON DELETE CASCADE
);


-- =========================================
-- RECOMMENDATION HISTORY
-- =========================================

CREATE TABLE recommendation_history (
    id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL,
    article_id BIGINT NOT NULL,

    score FLOAT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_recommendation_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_recommendation_article
        FOREIGN KEY (article_id)
        REFERENCES articles(id)
        ON DELETE CASCADE
);