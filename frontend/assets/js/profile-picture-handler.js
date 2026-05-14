(function () {
  if (!window.KazixProfilePicture) {
    window.KazixProfilePicture = {};
  }

  const API_BASE = window.KAZIX_API_BASE || 'https://kazix.onrender.com';

  /**
   * Handles profile picture upload and management.
   * Integrates with the image editor modal.
   */
  class ProfilePictureHandler {
    constructor() {
      this.isUploading = false;
      this.currentEditFile = null;
      this.editCanvasContext = null;
      this.originalImageData = null;
      this.setupEventListeners();
    }

    /**
     * Setup event listeners for avatar edit buttons
     */
    setupEventListeners() {
      document.addEventListener('click', (e) => {
        if (e.target.closest('.p-avatar-edit')) {
          this.openImageEditorModal();
        }
      });
    }

    /**
     * Open the image editor modal
     */
    openImageEditorModal() {
      let modal = document.getElementById('imageEditorModal');
      if (!modal) {
        modal = this.createEditorModal();
        document.body.appendChild(modal);
      }
      modal.style.display = 'flex';
      document.body.style.overflow = 'hidden';

      // Reset form
      document.getElementById('pictureFileInput').value = '';
      document.getElementById('imagePreview').innerHTML = '';
      document.getElementById('editorControls').style.display = 'none';
      this.resetEditorState();
    }

    /**
     * Create the image editor modal HTML
     */
    createEditorModal() {
      const modal = document.createElement('div');
      modal.id = 'imageEditorModal';
      modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.7);
        display: none;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        padding: 1rem;
      `;

      modal.innerHTML = `
        <div style="background: white; border-radius: 8px; max-width: 600px; width: 100%; max-height: 90vh; overflow-y: auto; box-shadow: 0 10px 40px rgba(0,0,0,0.2);">
          <div style="padding: 1.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; sticky; top: 0; background: white;">
            <h2 style="margin: 0; font-family: 'Syne', sans-serif; font-weight: 800; font-size: 1.25rem;">Upload Profile Picture</h2>
            <button class="modal-close" style="background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--muted);">✕</button>
          </div>

          <div style="padding: 1.5rem;">
            <!-- File Input -->
            <div style="margin-bottom: 1.5rem;">
              <label style="display: block; font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem;">Select Image (JPG or PNG)</label>
              <input id="pictureFileInput" type="file" accept="image/jpeg,image/png" style="display: block; width: 100%; padding: 0.75rem; border: 2px dashed var(--border); border-radius: 4px; cursor: pointer;" />
              <div id="fileError" style="color: var(--rust); font-size: 0.8rem; margin-top: 0.5rem; display: none;"></div>
            </div>

            <!-- Preview & Controls -->
            <div id="editorControls" style="display: none;">
              <!-- Canvas for preview -->
              <div style="margin-bottom: 1.5rem; background: #f5f5f5; border-radius: 4px; overflow: hidden; display: flex; align-items: center; justify-content: center; min-height: 300px; position: relative;">
                <canvas id="imageCanvas" style="max-width: 100%; max-height: 400px; display: none;"></canvas>
                <img id="imagePreview" style="max-width: 100%; max-height: 400px;" />
              </div>

              <!-- Control Buttons & Sliders -->
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 1.5rem;">
                <button id="rotateLeftBtn" style="padding: 0.75rem; background: var(--cream); border: 1px solid var(--border); border-radius: 4px; font-weight: 600; cursor: pointer; transition: all 0.2s;">↺ Rotate</button>
                <button id="flipHBtn" style="padding: 0.75rem; background: var(--cream); border: 1px solid var(--border); border-radius: 4px; font-weight: 600; cursor: pointer; transition: all 0.2s;">↔ Flip H</button>
                <button id="flipVBtn" style="padding: 0.75rem; background: var(--cream); border: 1px solid var(--border); border-radius: 4px; font-weight: 600; cursor: pointer; transition: all 0.2s;">↕ Flip V</button>
                <button id="resetBtn" style="padding: 0.75rem; background: var(--cream); border: 1px solid var(--border); border-radius: 4px; font-weight: 600; cursor: pointer; transition: all 0.2s;">↻ Reset</button>
              </div>

              <!-- Adjustment Sliders -->
              <div style="margin-bottom: 1.5rem;">
                <div style="margin-bottom: 1rem;">
                  <label style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 0.4rem;">
                    <span>Brightness</span>
                    <span id="brightnessValue">100%</span>
                  </label>
                  <input id="brightnessSlider" type="range" min="0" max="200" value="100" style="width: 100%; cursor: pointer;" />
                </div>

                <div style="margin-bottom: 1rem;">
                  <label style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 0.4rem;">
                    <span>Contrast</span>
                    <span id="contrastValue">100%</span>
                  </label>
                  <input id="contrastSlider" type="range" min="0" max="200" value="100" style="width: 100%; cursor: pointer;" />
                </div>

                <div>
                  <label style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 0.4rem;">
                    <span>Saturation</span>
                    <span id="saturationValue">100%</span>
                  </label>
                  <input id="saturationSlider" type="range" min="0" max="200" value="100" style="width: 100%; cursor: pointer;" />
                </div>
              </div>

              <!-- Upload Progress -->
              <div id="uploadProgress" style="display: none; margin-bottom: 1.5rem;">
                <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 0.5rem;">
                  <span>Uploading...</span>
                  <span id="uploadPercent">0%</span>
                </div>
                <div style="height: 4px; background: var(--border); border-radius: 2px; overflow: hidden;">
                  <div id="uploadBar" style="height: 100%; background: var(--green); width: 0%; transition: width 0.2s;"></div>
                </div>
              </div>

              <!-- Error Message -->
              <div id="uploadError" style="background: rgba(192,57,43,0.1); border: 1px solid rgba(192,57,43,0.3); border-radius: 4px; padding: 0.75rem; color: var(--rust); font-size: 0.85rem; margin-bottom: 1.5rem; display: none;"></div>
            </div>

            <!-- Buttons -->
            <div style="display: flex; gap: 0.75rem; justify-content: flex-end;">
              <button class="modal-cancel" style="padding: 0.75rem 1.5rem; background: transparent; border: 1px solid var(--border); border-radius: 4px; font-family: 'Syne', sans-serif; font-weight: 600; cursor: pointer; transition: all 0.2s;">Cancel</button>
              <button id="uploadBtn" style="padding: 0.75rem 1.5rem; background: var(--ink); color: #F5F0E8; border: none; border-radius: 4px; font-family: 'Syne', sans-serif; font-weight: 600; cursor: pointer; transition: all 0.2s; display: none;">Upload Picture</button>
            </div>
          </div>
        </div>
      `;

      this.setupModalListeners(modal);
      return modal;
    }

    /**
     * Setup modal event listeners
     */
    setupModalListeners(modal) {
      const closeBtn = modal.querySelector('.modal-close');
      const cancelBtn = modal.querySelector('.modal-cancel');
      const fileInput = modal.querySelector('#pictureFileInput');
      const uploadBtn = modal.querySelector('#uploadBtn');

      closeBtn.addEventListener('click', () => this.closeModal());
      cancelBtn.addEventListener('click', () => this.closeModal());

      fileInput.addEventListener('change', (e) => this.handleFileSelect(e));

      uploadBtn.addEventListener('click', () => this.uploadPicture());

      // Editor controls
      modal.querySelector('#rotateLeftBtn').addEventListener('click', () => this.rotateImage(-90));
      modal.querySelector('#flipHBtn').addEventListener('click', () => this.flipImageH());
      modal.querySelector('#flipVBtn').addEventListener('click', () => this.flipImageV());
      modal.querySelector('#resetBtn').addEventListener('click', () => this.resetImage());

      // Sliders
      modal.querySelector('#brightnessSlider').addEventListener('input', (e) => {
        document.getElementById('brightnessValue').textContent = e.target.value + '%';
        this.updateImageFilters();
      });
      modal.querySelector('#contrastSlider').addEventListener('input', (e) => {
        document.getElementById('contrastValue').textContent = e.target.value + '%';
        this.updateImageFilters();
      });
      modal.querySelector('#saturationSlider').addEventListener('input', (e) => {
        document.getElementById('saturationValue').textContent = e.target.value + '%';
        this.updateImageFilters();
      });

      // Close on outside click
      modal.addEventListener('click', (e) => {
        if (e.target === modal) this.closeModal();
      });
    }

    /**
     * Handle file selection
     */
    handleFileSelect(event) {
      const file = event.target.files[0];
      if (!file) return;

      // Validate file
      if (!['image/jpeg', 'image/png'].includes(file.type)) {
        this.showFileError('Please select a JPG or PNG image.');
        return;
      }

      if (file.size > 5 * 1024 * 1024) {
        this.showFileError('File is too large. Maximum size is 5 MB.');
        return;
      }

      this.currentEditFile = file;
      const reader = new FileReader();
      reader.onload = (e) => this.loadImageToEditor(e.target.result);
      reader.readAsDataURL(file);
    }

    /**
     * Load image into editor
     */
    loadImageToEditor(dataUrl) {
      const img = new Image();
      img.onload = () => {
        const canvas = document.getElementById('imageCanvas');
        canvas.width = img.width;
        canvas.height = img.height;

        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);

        this.originalImageData = {
          dataUrl: dataUrl,
          width: img.width,
          height: img.height,
          rotation: 0,
          flipH: false,
          flipV: false,
        };

        this.editCanvasContext = ctx;

        // Show preview
        document.getElementById('imagePreview').src = dataUrl;
        document.getElementById('editorControls').style.display = 'block';
        document.getElementById('uploadBtn').style.display = 'block';
        document.getElementById('fileError').style.display = 'none';

        // Reset sliders
        document.getElementById('brightnessSlider').value = 100;
        document.getElementById('contrastSlider').value = 100;
        document.getElementById('saturationSlider').value = 100;
      };
      img.src = dataUrl;
    }

    /**
     * Rotate image
     */
    rotateImage(degrees) {
      if (!this.originalImageData) return;
      this.originalImageData.rotation += degrees;
      this.updateImagePreview();
    }

    /**
     * Flip image horizontally
     */
    flipImageH() {
      if (!this.originalImageData) return;
      this.originalImageData.flipH = !this.originalImageData.flipH;
      this.updateImagePreview();
    }

    /**
     * Flip image vertically
     */
    flipImageV() {
      if (!this.originalImageData) return;
      this.originalImageData.flipV = !this.originalImageData.flipV;
      this.updateImagePreview();
    }

    /**
     * Reset image to original
     */
    resetImage() {
      if (!this.originalImageData) return;
      this.originalImageData.rotation = 0;
      this.originalImageData.flipH = false;
      this.originalImageData.flipV = false;
      document.getElementById('brightnessSlider').value = 100;
      document.getElementById('contrastSlider').value = 100;
      document.getElementById('saturationSlider').value = 100;
      document.getElementById('brightnessValue').textContent = '100%';
      document.getElementById('contrastValue').textContent = '100%';
      document.getElementById('saturationValue').textContent = '100%';
      this.updateImagePreview();
    }

    /**
     * Update image preview with transformations
     */
    updateImagePreview() {
      if (!this.originalImageData) return;
      const img = new Image();
      img.onload = () => {
        const canvas = document.getElementById('imageCanvas');
        const rotation = this.originalImageData.rotation;
        const flipH = this.originalImageData.flipH;
        const flipV = this.originalImageData.flipV;

        // Adjust canvas size for rotation
        let w = img.width;
        let h = img.height;
        if (Math.abs(rotation) % 180 === 90) {
          [w, h] = [h, w];
        }

        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.save();

        // Apply transformations
        ctx.translate(w / 2, h / 2);
        if (flipH) ctx.scale(-1, 1);
        if (flipV) ctx.scale(1, -1);
        ctx.rotate((rotation * Math.PI) / 180);
        ctx.drawImage(img, -img.width / 2, -img.height / 2);

        ctx.restore();

        this.editCanvasContext = ctx;
        this.updateImageFilters();
      };
      img.src = this.originalImageData.dataUrl;
    }

    /**
     * Update image filters (brightness, contrast, saturation)
     */
    updateImageFilters() {
      if (!this.originalImageData) return;
      const canvas = document.getElementById('imageCanvas');
      const brightness = parseInt(document.getElementById('brightnessSlider').value);
      const contrast = parseInt(document.getElementById('contrastSlider').value);
      const saturation = parseInt(document.getElementById('saturationSlider').value);

      const filter = `brightness(${brightness}%) contrast(${contrast}%) saturate(${saturation}%)`;
      canvas.style.filter = filter;
    }

    /**
     * Upload picture to backend
     */
    async uploadPicture() {
      if (!this.currentEditFile) {
        this.showUploadError('No file selected.');
        return;
      }

      if (this.isUploading) return;

      const token = localStorage.getItem('kazix_access_token');
      if (!token) {
        this.showUploadError('Please sign in to upload a profile picture.');
        return;
      }

      this.isUploading = true;
      document.getElementById('uploadBtn').disabled = true;
      document.getElementById('uploadProgress').style.display = 'block';
      document.getElementById('uploadError').style.display = 'none';

      try {
        const formData = new FormData();
        formData.append('file', this.currentEditFile);

        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            document.getElementById('uploadPercent').textContent = percent + '%';
            document.getElementById('uploadBar').style.width = percent + '%';
          }
        });

        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            const response = JSON.parse(xhr.responseText);
            this.onUploadSuccess(response);
          } else {
            const error = JSON.parse(xhr.responseText);
            this.showUploadError(error.detail || 'Upload failed. Please try again.');
            this.isUploading = false;
            document.getElementById('uploadBtn').disabled = false;
            document.getElementById('uploadProgress').style.display = 'none';
          }
        });

        xhr.addEventListener('error', () => {
          this.showUploadError('Network error. Please check your connection.');
          this.isUploading = false;
          document.getElementById('uploadBtn').disabled = false;
          document.getElementById('uploadProgress').style.display = 'none';
        });

        xhr.open('POST', `${API_BASE}/v1/profiles/picture`);
        xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        xhr.send(formData);
      } catch (error) {
        this.showUploadError(error.message || 'Upload failed.');
        this.isUploading = false;
        document.getElementById('uploadBtn').disabled = false;
        document.getElementById('uploadProgress').style.display = 'none';
      }
    }

    /**
     * Handle successful upload
     */
    onUploadSuccess(profileData) {
      this.isUploading = false;
      this.closeModal();

      // Update profile avatar display
      if (profileData?.profile?.avatar_url) {
        const avatars = document.querySelectorAll('.p-avatar');
        avatars.forEach((avatar) => {
          avatar.style.backgroundImage = `url('${profileData.profile.avatar_url}')`;
          avatar.style.backgroundSize = 'cover';
          avatar.style.backgroundPosition = 'center';
          avatar.textContent = ''; // Clear emoji
        });

        // Show success message
        if (window.KazixErrorHandler) {
          window.KazixErrorHandler.showSuccess('Profile picture updated successfully!');
        }
      }
    }

    /**
     * Show file input error
     */
    showFileError(message) {
      const errorEl = document.getElementById('fileError');
      if (errorEl) {
        errorEl.textContent = message;
        errorEl.style.display = 'block';
      }
    }

    /**
     * Show upload error
     */
    showUploadError(message) {
      const errorEl = document.getElementById('uploadError');
      if (errorEl) {
        errorEl.textContent = message;
        errorEl.style.display = 'block';
      }
    }

    /**
     * Reset editor state
     */
    resetEditorState() {
      this.isUploading = false;
      this.currentEditFile = null;
      this.editCanvasContext = null;
      this.originalImageData = null;
    }

    /**
     * Close modal
     */
    closeModal() {
      const modal = document.getElementById('imageEditorModal');
      if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
        this.resetEditorState();
      }
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      window.KazixProfilePicture.handler = new ProfilePictureHandler();
    });
  } else {
    window.KazixProfilePicture.handler = new ProfilePictureHandler();
  }

  // Export for external use
  window.KazixProfilePicture.openEditor = () => {
    if (window.KazixProfilePicture.handler) {
      window.KazixProfilePicture.handler.openImageEditorModal();
    }
  };
})();
