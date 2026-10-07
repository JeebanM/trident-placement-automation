import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import PlacementPost, ExtractedData

@pytest.mark.asyncio
async def test_api_post_extracted_data_association(
    async_client: AsyncClient,
    db_session: AsyncSession
):
    """
    Regression test to prove that GET /api/posts strictly associates
    a post with its EXACT corresponding ExtractedData via post_id.
    """
    # Insert Post 1 (Alok)
    post1 = PlacementPost(title="Post 1 Alok", post_url="http://alok", processing_status="done", notice_hash="hash1")
    # Insert Post 2 (DH Bars)
    post2 = PlacementPost(title="Post 2 DH Bars", post_url="http://dhbars", processing_status="done", notice_hash="hash2")
    # Insert Post 7 (Alok 2)
    post7 = PlacementPost(title="Post 7 Alok 2", post_url="http://alok2", processing_status="done", notice_hash="hash7")
    
    db_session.add_all([post1, post2, post7])
    await db_session.flush()

    # Now manually insert the Extractions, ensuring post.id == extracted.post_id
    ext1 = ExtractedData(post_id=post1.id, company_name="Alok Ingots from DB", extraction_model="test")
    ext2 = ExtractedData(post_id=post2.id, company_name="DH Bars from DB", extraction_model="test")
    ext7 = ExtractedData(post_id=post7.id, company_name="Alok 2 from DB", extraction_model="test")
    
    db_session.add_all([ext1, ext2, ext7])
    await db_session.commit()

    # Call the API
    response = await async_client.get("/api/posts?limit=10")
    assert response.status_code == 200
    
    data = response.json()
    # Map by post title for easy assertion
    results_by_title = {item["title"]: item["company"] for item in data}

    # Verify that the correct extraction is joined to the correct post
    assert results_by_title["Post 1 Alok"] == "Alok Ingots from DB", "Data association bug: Post 1 got the wrong company!"
    assert results_by_title["Post 2 DH Bars"] == "DH Bars from DB"
    assert results_by_title["Post 7 Alok 2"] == "Alok 2 from DB"
