/**
 * PageManager - Centralized page initialization and common operations
 * Reduces boilerplate code across all JavaScript modules
 */
window.PageManager = class PageManager {
    constructor(config) {
        this.config = {
            titleKey: '',
            fallbackTitle: '',
            pageTranslations: null,
            autoTranslate: true,
            enableLanguageChange: true,
            customTranslationHandler: null,
            ...config
        };
        
        this.init();
    }
    
    init() {
        // Standard page initialization
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.initializePage());
        } else {
            this.initializePage();
        }
    }
    
    initializePage() {
        // Initialize page title and translations
        if (this.config.titleKey && this.config.fallbackTitle) {
            window.initializePage({
                titleKey: this.config.titleKey,
                fallbackTitle: this.config.fallbackTitle,
                pageTranslations: this.config.pageTranslations
            });
        }
        
        // Apply initial translations
        if (this.config.autoTranslate) {
            updatePageTranslations();
        }
        
        // Setup language change listener
        if (this.config.enableLanguageChange) {
            window.addEventListener('languageChanged', () => {
                if (this.config.customTranslationHandler) {
                    this.config.customTranslationHandler();
                } else {
                    updatePageTranslations();
                }
            });
        }
        
        // Call custom initialization if provided
        if (this.config.onInit) {
            this.config.onInit();
        }
    }
    
    // Helper methods for common operations
    static getElementById(id) {
        return document.getElementById(id);
    }
    
    static querySelector(selector) {
        return document.querySelector(selector);
    }
    
    static querySelectorAll(selector) {
        return document.querySelectorAll(selector);
    }
    
    static addClass(element, className) {
        if (element) element.classList.add(className);
    }
    
    static removeClass(element, className) {
        if (element) element.classList.remove(className);
    }
    
    static toggleClass(element, className) {
        if (element) element.classList.toggle(className);
    }
    
    static show(element) {
        if (element) element.style.display = 'block';
    }
    
    static hide(element) {
        if (element) element.style.display = 'none';
    }
    
    static setValue(element, value) {
        if (element) element.value = value;
    }
    
    static getValue(element) {
        return element ? element.value : '';
    }
    
    static setHTML(element, html) {
        if (element) element.innerHTML = html;
    }
    
    static setText(element, text) {
        if (element) element.textContent = text;
    }
};