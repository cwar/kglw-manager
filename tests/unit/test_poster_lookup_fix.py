"""Test poster lookup enhancements for Kometa sync."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from kglw_manager.sources import KGLWNetSource


class TestPosterLookupEnhancement:
    """Test enhanced poster lookup with date range and location matching."""
    
    @pytest.fixture
    def kglw_source(self):
        """Create KGLWNetSource for testing."""
        return KGLWNetSource()
    
    def test_exact_date_match_takes_priority(self, kglw_source):
        """Test that exact date matches are returned first."""
        mock_uploads = [
            {
                'showdate': '2024-03-15',
                'upload_type': 'poster-art',
                'URL': 'https://kglw.net/i/exact-match.jpg',
                'img_name': 'Poster Art, 2024-03-15 - Santiago, Chile'
            },
            {
                'showdate': '2024-03-14',
                'upload_type': 'poster-art', 
                'URL': 'https://kglw.net/i/nearby-match.jpg',
                'img_name': 'Poster Art, 2024-03-14 - Santiago, Chile'
            }
        ]
        
        with patch.object(kglw_source.session, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_uploads
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = kglw_source.get_show_poster('2024-03-15')
            
        assert result == 'https://kglw.net/i/exact-match.jpg'
    
    def test_location_matching_in_date_range(self, kglw_source):
        """Test that location matching works when no exact date match."""
        mock_uploads = [
            {
                'showdate': '2024-03-14',  # Day before show
                'upload_type': 'poster-art',
                'URL': 'https://kglw.net/i/santiago-poster.jpg',
                'img_name': 'Poster Art, 2024-03-14 - Santiago, Chile'
            },
            {
                'showdate': '2024-03-14',  # Same date, different location
                'upload_type': 'poster-art',
                'URL': 'https://kglw.net/i/milan-poster.jpg', 
                'img_name': 'Poster Art, 2024-03-14 - Milan, Italy'
            }
        ]
        
        # Mock show info to provide location context
        mock_show_info = {'showdate': '2024-03-15', 'city': 'Santiago'}
        
        with patch.object(kglw_source.session, 'get') as mock_get:
            with patch.object(kglw_source, '_find_show_by_date', return_value=mock_show_info):
                mock_response = Mock()
                mock_response.json.return_value = mock_uploads
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                result = kglw_source.get_show_poster('2024-03-15')
                
        # Should find Santiago poster, not Milan
        assert result == 'https://kglw.net/i/santiago-poster.jpg'
    
    def test_date_proximity_fallback(self, kglw_source):
        """Test fallback to nearby dates when location matching fails."""
        mock_uploads = [
            {
                'showdate': '2024-03-14',  # Day before (within ±2 days range)
                'upload_type': 'poster-art',
                'URL': 'https://kglw.net/i/nearby-poster.jpg',
                'img_name': 'Poster Art, 2024-03-14 - Different City'
            }
        ]
        
        # Mock show info with no city info to trigger no-location-constraint fallback
        mock_show_info = {'showdate': '2024-03-15', 'permalink': 'test-show'}
        
        # Mock that show page scraping returns None (no poster found on page)
        with patch.object(kglw_source, '_get_poster_from_show_page', return_value=None):
            with patch.object(kglw_source.session, 'get') as mock_get:
                with patch.object(kglw_source, '_find_show_by_date', return_value=mock_show_info):
                    mock_response = Mock()
                    mock_response.json.return_value = mock_uploads
                    mock_response.raise_for_status.return_value = None
                    mock_get.return_value = mock_response
                    
                    result = kglw_source.get_show_poster('2024-03-15')
                    
        # Should find nearby poster as fallback from uploads API
        assert result == 'https://kglw.net/i/nearby-poster.jpg'
    
    def test_no_poster_found_returns_none(self, kglw_source):
        """Test that None is returned when no posters found."""
        mock_uploads = [
            {
                'showdate': '2024-03-01',  # Too far from target date
                'upload_type': 'poster-art',
                'URL': 'https://kglw.net/i/distant-poster.jpg',
                'img_name': 'Poster Art, 2024-03-01'
            }
        ]
        
        with patch.object(kglw_source.session, 'get') as mock_get:
            with patch.object(kglw_source, '_find_show_by_date', return_value=None):
                mock_response = Mock()
                mock_response.json.return_value = mock_uploads
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                result = kglw_source.get_show_poster('2024-03-15')
                
        assert result is None
    
    def test_escaped_slash_handling(self, kglw_source):
        """Test that escaped slashes in URLs are properly handled."""
        mock_uploads = [
            {
                'showdate': '2024-03-15',
                'upload_type': 'poster-art',
                'URL': 'https:\\/\\/kglw.net\\/i\\/escaped-slashes.jpg',  # Escaped slashes
                'img_name': 'Test Poster'
            }
        ]
        
        with patch.object(kglw_source.session, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_uploads
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = kglw_source.get_show_poster('2024-03-15')
            
        # Escaped slashes should be cleaned up
        assert result == 'https://kglw.net/i/escaped-slashes.jpg'
    
    def test_handles_api_errors_gracefully(self, kglw_source):
        """Test that API errors are handled gracefully."""
        with patch.object(kglw_source.session, 'get') as mock_get:
            mock_get.side_effect = Exception("Network error")
            
            result = kglw_source.get_show_poster('2024-03-15')
            
        assert result is None
    
    def test_ignores_non_poster_uploads(self, kglw_source):
        """Test that non-poster uploads are ignored."""
        mock_uploads = [
            {
                'showdate': '2024-03-15',
                'upload_type': 'photo',  # Not poster-art
                'URL': 'https://kglw.net/i/photo.jpg',
                'img_name': 'Concert Photo'
            },
            {
                'showdate': '2024-03-15',
                'upload_type': 'poster-art',  # This should be found
                'URL': 'https://kglw.net/i/poster.jpg',
                'img_name': 'Poster Art'
            }
        ]
        
        with patch.object(kglw_source.session, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_uploads
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = kglw_source.get_show_poster('2024-03-15')
            
        # Should only find poster-art, not photo
        assert result == 'https://kglw.net/i/poster.jpg'
    
    def test_poster_from_show_page_scraping(self, kglw_source):
        """Test scraping poster from individual show page."""
        # Mock show info with permalink
        mock_show_info = {
            'showdate': '2024-03-15', 
            'permalink': 'king-gizzard-the-lizard-wizard-march-15-2024-parque-cerrillos-santiago-chile'
        }
        
        # Mock HTML content with external poster link
        mock_html = '''
        <html>
        <body>
            <div class="show-content">
                <img src="https://www.livenationentertainment.com/wp-content/uploads/2023/11/LOLLA-CHILE-819x1024.jpg" 
                     alt="Lollapalooza Chile Poster" />
                <p>Show information...</p>
            </div>
        </body>
        </html>
        '''
        
        with patch.object(kglw_source, '_find_show_by_date', return_value=mock_show_info):
            with patch.object(kglw_source.session, 'get') as mock_get:
                # Mock uploads API to return no results (will fall back to show page)
                mock_uploads_response = Mock()
                mock_uploads_response.json.return_value = []
                mock_uploads_response.raise_for_status.return_value = None
                
                # Mock show page response
                mock_page_response = Mock()
                mock_page_response.content = mock_html.encode('utf-8')
                mock_page_response.raise_for_status.return_value = None
                
                # Return different responses for different URLs
                def side_effect(url, **kwargs):
                    if 'uploads.json' in url:
                        return mock_uploads_response
                    else:  # Show page
                        return mock_page_response
                        
                mock_get.side_effect = side_effect
                
                result = kglw_source.get_show_poster('2024-03-15')
                
        # Should find the external poster link
        assert result == 'https://www.livenationentertainment.com/wp-content/uploads/2023/11/LOLLA-CHILE-819x1024.jpg'
    
    def test_show_page_poster_prioritizes_lolla_images(self, kglw_source):
        """Test that Lollapalooza posters are correctly identified."""
        mock_show_info = {
            'showdate': '2024-03-15',
            'permalink': 'test-show'
        }
        
        mock_html = '''
        <html>
        <body>
            <img src="https://example.com/random-image.jpg" alt="Random Image" />
            <img src="https://cdn.lollapalooza.com/poster.jpg" alt="Lolla Poster" />
            <img src="https://example.com/another-image.jpg" alt="Another Image" />
        </body>
        </html>
        '''
        
        with patch.object(kglw_source, '_find_show_by_date', return_value=mock_show_info):
            with patch.object(kglw_source, '_get_poster_from_uploads_api', return_value=None):
                with patch.object(kglw_source.session, 'get') as mock_get:
                    mock_response = Mock()
                    mock_response.content = mock_html.encode('utf-8')
                    mock_response.raise_for_status.return_value = None
                    mock_get.return_value = mock_response
                    
                    result = kglw_source.get_show_poster('2024-03-15')
                    
        # Should find the Lolla poster specifically
        assert result == 'https://cdn.lollapalooza.com/poster.jpg'
    
    def test_show_page_handles_protocol_relative_urls(self, kglw_source):
        """Test that protocol-relative URLs are handled correctly."""
        mock_show_info = {
            'showdate': '2024-03-15',
            'permalink': 'test-show'
        }
        
        mock_html = '''
        <html>
        <body>
            <img src="//cdn.example.com/lolla-poster.jpg" alt="Festival Poster" />
        </body>
        </html>
        '''
        
        with patch.object(kglw_source, '_find_show_by_date', return_value=mock_show_info):
            with patch.object(kglw_source, '_get_poster_from_uploads_api', return_value=None):
                with patch.object(kglw_source.session, 'get') as mock_get:
                    mock_response = Mock()
                    mock_response.content = mock_html.encode('utf-8')
                    mock_response.raise_for_status.return_value = None
                    mock_get.return_value = mock_response
                    
                    result = kglw_source.get_show_poster('2024-03-15')
                    
        # Should convert protocol-relative URL to absolute
        assert result == 'https://cdn.example.com/lolla-poster.jpg'