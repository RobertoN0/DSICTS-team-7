package com.example.jitlab.api.mongo;
import lombok.Data;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Data
@Document(collection = "messages")
public class Message {
    @Id
    private String id;
    private String text;

    public Message(String text) {
        this.text = text;
    }
}