#include <stdio.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_random.h"

static const char *TAG = "CSI_SENDER";

// Generate a random float between -1.0 and 1.0 using hardware ESP random
float get_random_float() {
    uint32_t r = esp_random();
    return ((float)r / (float)UINT32_MAX) * 2.0f - 1.0f;
}

void app_main(void) {
    ESP_LOGINFO(TAG, "ESP32 CSI Gemma Filter - Dummy Serial CSI Source Started.");
    ESP_LOGINFO(TAG, "Format: timestamp,rssi,csi_0,csi_1,csi_2,csi_3,csi_4,csi_5");
    ESP_LOGINFO(TAG, "Real ESP-IDF CSI callback implementation will be added in Milestone 2.");

    float time_sec = 0.0f;
    const float dt = 0.1f; // 100ms interval
    
    while (1) {
        // Get system timestamp in milliseconds
        int64_t timestamp = esp_timer_get_time() / 1000;
        
        // 1. Smooth baseline movement
        float baseline = 20.0f + 5.0f * sinf(2.0f * M_PI * 0.05f * time_sec);
        
        // 2. High-frequency random noise
        float noise = get_random_float() * 1.5f;
        
        // 3. Spikes (outliers) - 5% chance
        float spike = 0.0f;
        if ((esp_random() % 100) < 5) {
            // Random spike of positive 30 or negative 25
            spike = ((esp_random() % 2) == 0) ? 30.0f : -25.0f;
        }
        
        float base_signal = baseline + noise + spike;
        
        // Simulated RSSI
        int rssi = -50 + (int)(0.2f * base_signal) + (esp_random() % 3 - 1);
        
        // Generate 6 subcarriers around base_signal with slight variations
        int csi[6];
        for (int i = 0; i < 6; i++) {
            float sub_variation = get_random_float() * 2.0f;
            csi[i] = (int)(base_signal + sub_variation);
            if (csi[i] < 1) {
                csi[i] = 1;
            }
        }
        
        // Output CSV-like format to Serial
        printf("%lld,%d,%d,%d,%d,%d,%d,%d\n",
               timestamp, rssi, csi[0], csi[1], csi[2], csi[3], csi[4], csi[5]);
        
        // Increment internal time and wait 100ms
        time_sec += dt;
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
