package com.example.jitlab.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Development-friendly CORS configuration. Allows all origins for ease of testing the demo page.
 * Remove or tighten in production.
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

  @Override
  public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/videos/**")
        .allowedOrigins("*")
        .allowedMethods("GET", "HEAD", "OPTIONS")
        .allowedHeaders("Range", "Content-Type", "Accept", "Origin")
        .exposedHeaders("Accept-Ranges", "Content-Range", "Content-Length", "Content-Type")
        .allowCredentials(false).maxAge(3600);

    // Allow static resources and demo page to be fetched from other origins too (optional)
    registry.addMapping("/play_range.html")
        .allowedOrigins("*")
        .allowedMethods("GET", "HEAD", "OPTIONS");
  }
}
