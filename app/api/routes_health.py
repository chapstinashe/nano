from flask import Blueprint, jsonify

from app.core.config import Config
from app.db.cosmos import _is_enabled

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "healthy",
            "embedding_model": Config.EMBEDDING_MODEL,
            "vector_backend": "azure_cosmos_vector_search",
            "vector_search": "VectorDistance",
            "cosmos_vectors_container": Config.COSMOS_VECTORS_CONTAINER,
            "embedding_dimensions": Config.EMBEDDING_DIMENSIONS,
            "cosmos_configured": _is_enabled(),
        }
    )
